import json
import queue
import re
import threading
import time
from pathlib import Path

from pynput import keyboard

from audio_io import Recorder
from commands_manager import match_command
from config import (
    APP_ALIASES,
    LAST_TRANSCRIPT_FILE,
    OCR_LANG_BOTH,
    TRANSCRIPTS_DIR,
    AUTO_MAP_ENABLED,
    AUTO_MAP_INTERVAL_SEC,
    APP_LAUNCH_TIMEOUT,
    AGENT_STEP_PAUSE_SEC,
    MAX_AGENT_STEPS,
    AGENT_CODING_STEP_PAUSE_SEC,
    MAX_CODING_AGENT_STEPS,
)
from action_executor import execute_action, _routine_section, _routine_value
from action_parsers import clean_youtube_query, detect_browser_request, looks_like_url, parse_discord_channel_request
from form_automation import parse_form_voice_request
from failure_ui import is_known_failure, report_action_failure
from engine import get_stt_label
from i18n import fail_reason_text, t
from llm_engine import (
    DANGEROUS_ACTIONS,
    infer_quick_actions,
    infer_structured_workflow,
    sanitize_planned_actions,
    enhance_coding_plan,
    is_coding_request,
    coding_plan_context,
    _fix_actions_from_text,
)
from platform_actions import (
    canonical_app_name,
    discord_post_in_server_channel,
    ensure_app_focus,
    get_active_window,
    get_last_gui_map_summary,
    get_open_windows,
    get_system_stats,
    gui_map_text,
    is_app_window_open,
    navigate_discord_server_channel,
    open_search,
    open_url_in_browser,
    open_youtube_first_result,
    send_hotkey,
    start_app_verified,
    type_text,
)
from web_automation import WebAutomation
from ui_popup import show_agent_step_popup, show_confirm_popup, show_status_popup
from confirmation import normalize_confirm_response
from agent_queue import AgentQueue
from agent_memory import load_memory, update_memory
from automation_settings import AutomationSettings
from action_verifier import verify_action
from debug_replay import write_debug_replay
from agent_error_policy import (
    ERROR_ABORT,
    ERROR_RETRY,
    ERROR_SKIP,
    decide_error_policy,
)
from utils import extract_tail_text, fold_text, parse_int_from_text


def write_transcript(ui_lang, audio_path: Path, result):
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    lines = []
    if result.language and result.language_probability is not None:
        lines.append(
            t(
                ui_lang,
                "detected_language",
                lang=result.language,
                prob=result.language_probability * 100,
            )
        )
        lines.append("-" * 50)
    if result.segments:
        for seg in result.segments:
            try:
                line = f"[{seg.start:.2f}s -> {seg.end:.2f}s] {seg.text}"
            except Exception:
                line = str(seg)
            lines.append(line)
    else:
        lines.append(result.text)

    content = "\n".join(lines) + "\n"
    out_path = TRANSCRIPTS_DIR / f"{audio_path.stem}_transcript.txt"
    out_path.write_text(content, encoding="utf-8")
    LAST_TRANSCRIPT_FILE.write_text(content, encoding="utf-8")
    print(t(ui_lang, "transcript_saved", path=out_path))
    print(t(ui_lang, "last_transcript_saved", path=LAST_TRANSCRIPT_FILE))


class ControlSession:
    def __init__(self, ui_lang, transcriber, commands, tts=None, llm=None, vlm=None, automation=None):
        self.ui_lang = ui_lang
        self.transcriber = transcriber
        self.commands = commands
        self.tts = tts
        self.llm = llm
        self.vlm = vlm
        self.automation = automation or AutomationSettings()
        self.web = WebAutomation()
        self.recorder = Recorder()
        self.recording = False
        self.processing = False
        self.lock = threading.Lock()
        self.confirm_lock = threading.Lock()
        self.pending_confirm = None
        self.cancel_event = threading.Event()
        self.job_queue = AgentQueue(self._run_job, cancel_callback=self.cancel_current)
        self._auto_map_thread = None
        self._auto_map_stop = threading.Event()

    def _build_state_context(self) -> str:
        try:
            windows = get_open_windows(limit=12)
        except Exception:
            windows = []
        try:
            active = get_active_window()
        except Exception:
            active = {}
        try:
            stats = get_system_stats()
        except Exception:
            stats = {}
        win_titles = []
        for item in windows:
            title = item.get("title") or ""
            exe = item.get("exe") or ""
            if title:
                win_titles.append(f"{title} ({exe})" if exe else title)
        active_text = ""
        if active:
            active_text = f"{active.get('title','')} ({active.get('exe','')})".strip()
        cpu = stats.get("cpu")
        ram = stats.get("ram")
        cpu_text = f"{cpu}%" if isinstance(cpu, int) else "unknown"
        ram_text = f"{ram}%" if isinstance(ram, int) else "unknown"
        try:
            from uia_automation import summarize_foreground

            uia_items = summarize_foreground(max_depth=2, max_items=40).get("items", [])
            uia_preview = [
                {
                    "name": item.get("name"),
                    "type": item.get("control_type"),
                    "rect": item.get("rect"),
                    "enabled": item.get("enabled"),
                    "focusable": item.get("focusable"),
                }
                for item in uia_items[:30]
                if item.get("name") or item.get("control_type")
            ]
            uia_context = "; UIA_CONTEXT_JSON: " + json.dumps(
                uia_preview, ensure_ascii=False
            )
        except Exception:
            uia_context = ""
        try:
            from page_context import format_page_context_for_llm

            page_context = format_page_context_for_llm(
                active=active, web=self.web, ui_lang=self.ui_lang
            )
        except Exception:
            page_context = ""
        base = (
            f"Current Windows: [{', '.join(win_titles)}]; "
            f"Active: {active_text}; CPU: {cpu_text}; RAM: {ram_text}"
            f"{uia_context}"
        )
        if page_context:
            return f"{base}; {page_context}"
        return base

    def _observer_context(self, action: str, fail_reason: str) -> str:
        active = get_active_window()
        active_text = f"{active.get('title','')} ({active.get('exe','')})".strip()
        summary = get_last_gui_map_summary()
        count = summary.get("count")
        path = summary.get("path")
        return (
            f"{fail_reason}; Active: {active_text}; "
            f"MapCount: {count}; MapPath: {path}"
        )

    def _request_needs_visual_context(self, text: str) -> bool:
        phrase = fold_text(text or "")
        visual_terms = (
            "tikla",
            "tıkla",
            "bas",
            "buton",
            "ekran",
            "sayfa",
            "form",
            "doldur",
            "giris",
            "giriş",
            "login",
            "sign in",
            "kayit",
            "kayıt",
            "sifre",
            "şifre",
            "password",
            "sign up",
            "signup",
            "register",
            "kaydol",
            "mesaj",
            "message",
            "dm",
            "gonder",
            "gönder",
            "discord",
            "browser",
            "tarayici",
            "tarayıcı",
        )
        return any(term in phrase for term in visual_terms)

    def _build_visual_context(self, goal: str) -> str:
        try:
            map_path, items = gui_map_text(ui_lang=self.ui_lang)
            ocr_preview = [
                {
                    "text": str(item.get("text", "")),
                    "left": item.get("left"),
                    "top": item.get("top"),
                    "width": item.get("width"),
                    "height": item.get("height"),
                }
                for item in items[:100]
                if str(item.get("text", "")).strip()
            ]
            if not self._vlm_ready():
                return "OCR_SCREEN_MAP_JSON: " + json.dumps(
                    {"map_path": map_path, "items": ocr_preview},
                    ensure_ascii=False,
                )
            observation, raw = self.vlm.observe_screen(
                image_path=map_path,
                goal=goal,
                ocr_items=items,
            )
        except Exception as exc:
            return f"VisualContextError: {exc}"
        if observation:
            return "VLM_SCREEN_OBSERVATION_JSON: " + json.dumps(
                observation, ensure_ascii=False
            )
        if raw:
            return f"VLM_SCREEN_OBSERVATION_RAW: {raw[:1200]}"
        return ""

    def _vlm_observe(self, action: str, value: str, goal: str | None) -> str:
        if not self._vlm_ready():
            return ""
        if not str(action).startswith("gui_"):
            return ""
        try:
            map_path, items = gui_map_text(ui_lang=self.ui_lang)
        except Exception:
            return ""
        observation, raw = self.vlm.observe_screen(
            image_path=map_path,
            goal=goal or value or "",
            ocr_items=items,
        )
        if observation:
            return "VLM_SCREEN_OBSERVATION_JSON: " + json.dumps(
                observation, ensure_ascii=False
            )
        return f"VLM_SCREEN_OBSERVATION_RAW: {raw[:1200]}" if raw else ""

    def _filter_completed_steps(
        self, actions: list[dict], completed_steps: list[dict]
    ) -> list[dict]:
        if not actions or not completed_steps:
            return actions
        completed = {
            (
                str(step.get("action", "")).strip().lower(),
                str(step.get("value", "") or "").strip().lower(),
            )
            for step in completed_steps
            if step.get("action")
        }
        filtered = []
        for item in actions:
            key = (
                str(item.get("action", "")).strip().lower(),
                str(item.get("value", "") or "").strip().lower(),
            )
            if key in completed:
                continue
            filtered.append(item)
        return filtered

    def _start_auto_map(self):
        if not AUTO_MAP_ENABLED:
            return
        if self._auto_map_thread and self._auto_map_thread.is_alive():
            return
        self._auto_map_stop.clear()

        def _loop():
            while not self._auto_map_stop.is_set():
                try:
                    gui_map_text(ui_lang=self.ui_lang)
                except Exception:
                    pass
                # sleep in small steps so we can stop quickly
                steps = max(1, int(AUTO_MAP_INTERVAL_SEC * 10))
                for _ in range(steps):
                    if self._auto_map_stop.is_set():
                        break
                    time.sleep(0.1)

        self._auto_map_thread = threading.Thread(target=_loop, daemon=True)
        self._auto_map_thread.start()

    def _stop_auto_map(self):
        self._auto_map_stop.set()

    def _speak_success(self):
        if self.tts:
            self.tts.speak_async(t(self.ui_lang, "tts_success"))

    def _speak_fail(self):
        if self.tts:
            self.tts.speak_async(t(self.ui_lang, "tts_fail"))

    def _print_active_models(self):
        stt_label = get_stt_label(self.transcriber)
        tts_status = self.tts.status_text(self.ui_lang) if self.tts else "-"
        llm_status = self.llm.status_text(self.ui_lang) if self.llm else "-"
        vlm_status = self.vlm.status_text(self.ui_lang) if self.vlm else "-"
        print(
            t(
                self.ui_lang,
                "active_models",
                stt=stt_label,
                tts=tts_status,
                llm=llm_status,
                vlm=vlm_status,
            )
        )

    def _planner(self):
        if (
            self.llm
            and getattr(self.llm, "enabled", False)
            and getattr(self.llm, "llm", None)
        ):
            return self.llm
        return None

    def _llm_ready(self) -> bool:
        return self._planner() is not None

    def _vlm_ready(self) -> bool:
        return bool(
            self.vlm
            and getattr(self.vlm, "enabled", False)
            and getattr(self.vlm, "llm", None)
        )

    def _needs_confirmation(self, action: str | None) -> bool:
        return action in DANGEROUS_ACTIONS

    def _await_confirmation(self, action: str, value: str | None) -> bool:
        event = threading.Event()
        with self.confirm_lock:
            self.pending_confirm = {"event": event, "response": None}
        message = t(self.ui_lang, "confirm_danger", action=action, value=value)
        print(message)

        def _set_response(response: str):
            with self.confirm_lock:
                if self.pending_confirm:
                    self.pending_confirm["response"] = response
                    self.pending_confirm["event"].set()

        show_confirm_popup(message, self.ui_lang, _set_response)
        event.wait()
        with self.confirm_lock:
            response = None
            if self.pending_confirm:
                response = self.pending_confirm.get("response")
            self.pending_confirm = None
        return response == "y"

    def handle_input_line(self, line: str) -> bool:
        line = (line or "").strip()
        if self.pending_confirm:
            response = normalize_confirm_response(line)
            if response:
                with self.confirm_lock:
                    if self.pending_confirm:
                        self.pending_confirm["response"] = response
                        self.pending_confirm["event"].set()
                return False
            print(t(self.ui_lang, "confirm_invalid"))
            return False
        if not line or line.lower() == "exit":
            return True
        lowered = line.lower()
        if lowered in ("queue", "sira", "siradakiler", "status"):
            current, pending = self.job_queue.status()
            if not current and pending == 0:
                print(t(self.ui_lang, "queue_empty"))
            else:
                current_label = (
                    t(self.ui_lang, "queue_current_yes")
                    if current
                    else t(self.ui_lang, "queue_current_no")
                )
                print(
                    t(
                        self.ui_lang,
                        "queue_status",
                        current=current_label,
                        pending=pending,
                    )
                )
                cur_job, pending_jobs, history_jobs = self.job_queue.detailed_snapshot()
                if cur_job:
                    print(
                        t(
                            self.ui_lang,
                            "queue_item_current",
                            id=cur_job.job_id,
                            text=cur_job.text,
                        )
                    )
                for job in pending_jobs:
                    print(
                        t(
                            self.ui_lang,
                            "queue_item_pending",
                            id=job.job_id,
                            text=job.text,
                        )
                    )
                for job in history_jobs:
                    if job.status in ("completed", "failed", "cancelled"):
                        print(
                            t(
                                self.ui_lang,
                                "queue_item_history",
                                id=job.job_id,
                                status=job.status,
                                text=job.text,
                                error=job.error,
                            )
                        )
            return False
        if lowered.startswith("cancel "):
            job_id = lowered.split(" ", 1)[1].strip()
            if self.job_queue.cancel(job_id):
                print(t(self.ui_lang, "queue_cancelled_id", id=job_id))
            else:
                print(t(self.ui_lang, "queue_not_found", id=job_id))
            return False
        if lowered in ("cancel", "iptal"):
            if self.job_queue.cancel_current():
                print(t(self.ui_lang, "queue_cancelled"))
            else:
                print(t(self.ui_lang, "queue_no_current"))
            return False
        if lowered in ("clear", "temizle"):
            self.job_queue.clear()
            print(t(self.ui_lang, "queue_cleared"))
            return False
        planner = self._planner()
        if planner and getattr(planner, "only_mode", False):
            self._enqueue_job(line, source="text", use_commands=False)
            return False
        if not planner and line:
            print(t(self.ui_lang, "llm_only_no_llm"))
        return False

    def cancel_current(self) -> bool:
        current, _ = self.job_queue.status()
        if not current:
            return False
        with self.lock:
            self.cancel_event.set()
        print(t(self.ui_lang, "llm_cancel_requested"))
        return True

    def _handle_llm_request(self, text: str, source_label: str) -> bool:
        planner = self._planner()
        if not planner:
            print(t(self.ui_lang, "llm_only_no_llm"))
            return False

        self.cancel_event.clear()
        print(t(self.ui_lang, "llm_debug_input", source=source_label, text=text))
        coding = is_coding_request(text)
        context = self._build_state_context()
        if coding:
            ctx = coding_plan_context(text)
            context = f"{context}; {ctx}" if context else ctx
        if self._request_needs_visual_context(text):
            visual_context = self._build_visual_context(text)
            if visual_context:
                context = f"{context}; {visual_context}"
        try:
            actions, goal, notes = planner.plan(text, context=context)
        except Exception as exc:
            print(t(self.ui_lang, "command_failed", error=f"planner: {exc}"))
            return True
        actions = self._maybe_prepend_focus(text, actions)
        actions = self._reorder_focus_after_start(actions)
        actions = enhance_coding_plan(text, actions)
        actions = sanitize_planned_actions(text, actions)
        step_cap = MAX_CODING_AGENT_STEPS if coding else MAX_AGENT_STEPS
        if len(actions) > step_cap:
            actions = actions[:step_cap]
            print(t(self.ui_lang, "agent_steps_trimmed", count=step_cap))
        if self.cancel_event.is_set():
            print(t(self.ui_lang, "llm_cancelled"))
            return True
        if goal:
            print(t(self.ui_lang, "agent_goal", goal=goal))
        if notes:
            print(t(self.ui_lang, "agent_notes", notes=notes))
        if not actions:
            if getattr(planner, "last_error", ""):
                print(t(self.ui_lang, "command_failed", error=planner.last_error))
            if getattr(planner, "last_raw", ""):
                print(t(self.ui_lang, "command_failed", error="planner returned empty/invalid JSON"))
            print(t(self.ui_lang, "llm_debug_invalid"))
            print(t(self.ui_lang, "llm_no_action"))
            return False

        print(t(self.ui_lang, "llm_multi_count", count=len(actions)))
        delay = float(getattr(planner, "multi_delay", 0.0) or 0.0)
        step_pause = AGENT_CODING_STEP_PAUSE_SEC if coding else AGENT_STEP_PAUSE_SEC
        replan_attempts = 0
        completed_steps: list[dict] = []
        performed: set[tuple[str, str]] = set()
        retry_counts: dict[tuple[str, str], int] = {}
        idx = 0
        needs_map = any(
            str(item.get("action", "")).startswith("gui_")
            or str(item.get("action", "")).startswith("web_")
            or str(item.get("action", "")) == "youtube_search"
            for item in actions
        )
        if needs_map:
            self._start_auto_map()
        try:
            while idx < len(actions):
                item = actions[idx]
                action = item.get("action")
                value = item.get("value") or ""
                critical = item.get("critical", True)
                if action in (None, "none"):
                    idx += 1
                    continue
                if action in ("start", "focus"):
                    if (action, value) in performed:
                        idx += 1
                        continue
                print(
                    t(
                        self.ui_lang,
                        "llm_action_step",
                        idx=idx + 1,
                        action=action,
                        value=value,
                    )
                )
                reason = item.get("reason")
                if reason:
                    print(t(self.ui_lang, "llm_debug_reason", reason=reason))

                if action == "routine_run":
                    routine_text = _routine_value(value)
                    if not routine_text:
                        ok = False
                        fail_reason = "routine_missing"
                    else:
                        print(t(self.ui_lang, "routine_found", name=value))
                        routine_context = self._build_state_context()
                        routine_actions, _routine_goal, routine_notes = planner.plan(
                            routine_text, context=routine_context
                        )
                        routine_actions = self._maybe_prepend_focus(routine_text, routine_actions)
                        routine_actions = self._reorder_focus_after_start(routine_actions)
                        if routine_notes:
                            print(t(self.ui_lang, "agent_notes", notes=routine_notes))
                        actions = actions[:idx] + routine_actions + actions[idx + 1 :]
                        print(t(self.ui_lang, "llm_multi_count", count=len(actions)))
                        continue

                if self._needs_confirmation(action):
                    confirmed = self._await_confirmation(action, value)
                    if not confirmed:
                        print(t(self.ui_lang, "command_cancelled"))
                        show_status_popup(
                            t(self.ui_lang, "command_popup_failed", error="cancelled")
                        )
                        self._speak_fail()
                        return True

                if self.cancel_event.is_set():
                    print(t(self.ui_lang, "llm_cancelled"))
                    return True

                show_agent_step_popup(
                    idx + 1,
                    len(actions),
                    str(action or ""),
                    str(value or ""),
                    ui_lang=self.ui_lang,
                )
                verification = {}
                try:
                    ok, fail_reason = execute_action(
                        action,
                        value,
                        tail_text=None,
                        ui_lang=self.ui_lang,
                        automation=self.automation,
                        web=self.web,
                    )
                except Exception as exc:
                    ok, fail_reason = False, str(exc)
                if ok:
                    verification = verify_action(action, value, web=self.web, ui_lang=self.ui_lang)
                    if not verification.get("ok", True):
                        ok = False
                        fail_reason = verification.get("reason", "verification_failed")
                if ok:
                    completed_steps.append(item)
                    if action in ("start", "focus"):
                        performed.add((action, value))
                    show_status_popup(
                        t(self.ui_lang, "command_popup_done", action=action or "")
                    )
                    self._speak_success()
                    idx += 1
                    if idx < len(actions):
                        time.sleep(max(0.0, step_pause))
                    if idx < len(actions) and delay > 0:
                        time.sleep(delay)
                    continue
                else:
                    base = str(fail_reason or "").split(":")[0].lower()
                    if base != "blocked":
                        report_action_failure(
                            self.ui_lang,
                            str(fail_reason),
                            value=value,
                            action=action,
                        )
                    if base == "blocked":
                        confirmed = self._await_confirmation(action, value)
                        if confirmed:
                            ok2, reason2 = execute_action(
                                action,
                                value,
                                tail_text=None,
                                ui_lang=self.ui_lang,
                                allow_blocked=True,
                                automation=self.automation,
                                web=self.web,
                            )
                            if ok2:
                                completed_steps.append(item)
                                show_status_popup(t(self.ui_lang, "command_popup_found"))
                                self._speak_success()
                                idx += 1
                                continue
                            print(t(self.ui_lang, "command_failed", error=reason2))
                        print(t(self.ui_lang, "open_blocked"))
                        show_status_popup(
                            t(
                                self.ui_lang,
                                "command_popup_failed",
                                error=fail_reason_text(self.ui_lang, "blocked"),
                            )
                        )
                    elif not is_known_failure(str(fail_reason)):
                        print(t(self.ui_lang, "unknown_action", action=action))
                        show_status_popup(
                            t(
                                self.ui_lang,
                                "command_popup_failed",
                                error=fail_reason_text(self.ui_lang, "unknown"),
                            )
                        )

                retry_key = (
                    str(action or "").strip().lower(),
                    str(value or "").strip().lower(),
                )
                policy = decide_error_policy(
                    action,
                    str(fail_reason),
                    bool(critical),
                    retry_counts.get(retry_key, 0),
                    replan_attempts,
                )
                vlm_note_for_replay = ""
                if str(action).startswith("gui_"):
                    vlm_note_for_replay = self._vlm_observe(action, value, goal)
                try:
                    from uia_automation import summarize_foreground

                    uia_summary = summarize_foreground(max_depth=3, max_items=80)
                except Exception:
                    uia_summary = {}
                try:
                    replay_path = write_debug_replay(
                        user_command=text,
                        plan=actions,
                        completed_steps=completed_steps,
                        failed_step=item,
                        error_policy=policy,
                        error=str(fail_reason),
                        verification=verification,
                        uia_summary=uia_summary,
                        vlm_note=vlm_note_for_replay,
                    )
                    print(t(self.ui_lang, "debug_replay_saved", path=replay_path))
                except Exception:
                    pass
                print(
                    t(
                        self.ui_lang,
                        "agent_error_policy",
                        decision=policy,
                        reason=fail_reason,
                    )
                )
                if policy == ERROR_RETRY:
                    retry_counts[retry_key] = retry_counts.get(retry_key, 0) + 1
                    time.sleep(0.7)
                    continue

                self._speak_fail()
                if policy == ERROR_SKIP:
                    idx += 1
                    continue
                if policy == ERROR_ABORT:
                    return True
                replan_attempts += 1
                print(t(self.ui_lang, "agent_replan", attempt=replan_attempts))
                error_ctx = str(fail_reason)
                if str(action).startswith("gui_"):
                    error_ctx = self._observer_context(action, str(fail_reason))
                    vlm_note = vlm_note_for_replay or self._vlm_observe(action, value, goal)
                    if vlm_note:
                        error_ctx = f"{error_ctx}; {vlm_note}"
                actions, goal, notes = planner.replan(
                    goal, completed_steps, item, error_ctx, original_text=text
                )
                actions = self._filter_completed_steps(actions, completed_steps)
                actions = self._maybe_prepend_focus(text, actions)
                actions = self._reorder_focus_after_start(actions)
                if notes:
                    print(t(self.ui_lang, "agent_notes", notes=notes))
                if not actions:
                    return True
                idx = 0
                print(t(self.ui_lang, "llm_multi_count", count=len(actions)))
                continue

            return True
        finally:
            if needs_map:
                self._stop_auto_map()

    def _start_recording(self):
        self.recorder.start()
        self.recording = True
        show_status_popup(t(self.ui_lang, "status_recording_started"))
        print(t(self.ui_lang, "recording_started"))

    def _stop_recording(self):
        self.recording = False
        out_path = self.recorder.stop_and_save()
        show_status_popup(t(self.ui_lang, "status_recording_stopped"))
        if out_path is None:
            print(t(self.ui_lang, "empty_recording"))
            return
        print(t(self.ui_lang, "recording_stopped", path=out_path))

        self.processing = True
        thread = threading.Thread(
            target=self._process_recording, args=(out_path,), daemon=True
        )
        thread.start()

    def _process_recording(self, audio_path: Path):
        try:
            self._print_active_models()
            result = self.transcriber.transcribe(audio_path, None)
            write_transcript(self.ui_lang, audio_path, result)
            if not result.text:
                print(t(self.ui_lang, "no_text"))
                return
            print(t(self.ui_lang, "detected_text", text=result.text))
            planner = self._planner()
            use_commands = not (planner and getattr(planner, "only_mode", False))
            self._enqueue_job(result.text, source="voice", use_commands=use_commands)
        finally:
            with self.lock:
                self.processing = False

    def _enqueue_job(self, text: str, source: str, use_commands: bool):
        job = self.job_queue.submit(text, source=source, use_commands=use_commands)
        _, pending = self.job_queue.status()
        print(
            t(
                self.ui_lang,
                "queue_added",
                count=pending,
                id=job.job_id,
            )
        )

    def _run_job(self, job):
        self.cancel_event.clear()
        print(
            t(
                self.ui_lang,
                "queue_item_current",
                id=job.job_id,
                text=job.text,
            )
        )
        source_label = (
            t(self.ui_lang, "llm_source_voice")
            if job.source == "voice"
            else t(self.ui_lang, "llm_source_text")
        )
        self._handle_text_request(job.text, source_label, job.use_commands)

    def _extract_discord_channel_request(self, text: str) -> tuple[str, str, str] | None:
        return parse_discord_channel_request(text)

    def _run_discord_channel_message(self, server: str, channel: str, message: str) -> bool:
        try:
            label = " / ".join(
                part for part in (server, channel, message[:24] if message else "") if part
            )
            show_status_popup(
                t(
                    self.ui_lang,
                    "command_popup_running",
                    action="discord",
                    value=label,
                )
            )
            if not is_app_window_open("discord"):
                ok, _method = start_app_verified("discord", ui_lang=self.ui_lang)
                if not ok:
                    show_status_popup(
                        t(self.ui_lang, "command_popup_failed", error="app_not_open")
                    )
                    self._speak_fail()
                    return True
                time.sleep(1.5)

            if message:
                ok = discord_post_in_server_channel(
                    server or None,
                    channel or None,
                    message,
                    ui_lang=self.ui_lang,
                )
            else:
                ok = navigate_discord_server_channel(
                    server or None,
                    channel or None,
                    ui_lang=self.ui_lang,
                )

            if not ok:
                show_status_popup(
                    t(self.ui_lang, "command_popup_failed", error="discord_navigation")
                )
                self._speak_fail()
                return True

            show_status_popup(t(self.ui_lang, "command_popup_done", action="discord"))
            self._speak_success()
            return True
        except Exception as exc:
            print(t(self.ui_lang, "command_failed", error=exc))
            show_status_popup(t(self.ui_lang, "command_popup_failed", error=exc))
            self._speak_fail()
            return True

    def _try_form_flow(self, text: str) -> bool:
        data = parse_form_voice_request(text)
        if not data:
            return False
        payload = ";".join(f"{key}={value}" for key, value in data.items())
        label = ", ".join(f"{key}={value}" for key, value in data.items() if key != "submit")
        show_status_popup(
            t(
                self.ui_lang,
                "command_popup_running",
                action="web_form_fill",
                value=label,
            )
        )
        try:
            ok, fail_reason = execute_action(
                "web_form_fill",
                payload,
                tail_text=None,
                ui_lang=self.ui_lang,
                automation=self.automation,
                web=self.web,
            )
        except Exception as exc:
            ok, fail_reason = False, str(exc)
        if ok:
            verification = verify_action(
                "web_form_fill", payload, web=self.web, ui_lang=self.ui_lang
            )
            if not verification.get("ok", True):
                ok = False
                fail_reason = verification.get("reason", "verification_failed")
        if not ok:
            report_action_failure(
                self.ui_lang,
                fail_reason or "unknown",
                action="web_form_fill",
            )
            show_status_popup(
                t(self.ui_lang, "command_popup_failed", error=fail_reason or "unknown")
            )
            self._speak_fail()
            return True
        show_status_popup(t(self.ui_lang, "command_popup_done", action="web_form_fill"))
        self._speak_success()
        return True

    def _extract_discord_request(self, text: str) -> tuple[str, str] | None:
        folded = fold_text(text or "")
        if "discord" not in folded:
            return None
        if any(w in folded for w in ("sunucu", "server")) and any(
            w in folded for w in ("kanal", "channel", "genel", "general")
        ):
            return None
        if not any(
            key in folded for key in ("mesaj", "message", "dm", "gonder", "gönder", "send", "yaz")
        ):
            return None

        msg = None
        import re

        for pattern in (r'"([^"]+)"', r"“([^”]+)”", r"'([^']+)'"):
            matches = re.findall(pattern, text)
            if matches:
                msg = matches[-1].strip()
        if not msg:
            raw_patterns = (
                r"(?:to)\s+[\w.-]{2,64}\s+(?:send|message|dm|write|type)\s+(.+?)$",
                r"(?:send|message|dm|write|type)\s+(.+?)\s+(?:to)\s+[\w.-]{2,64}$",
                r"(?:kişiye|kişisine|kisine|kisisine|kisiye|to)\s+(.+?)\s*(?:yaz|gönder|gonder|send)$",
                r"(?:mesaj(?:ı|i)?|message|dm)\s*(?:olarak)?\s+(.+?)$",
                r"(?:şunu|sunu|bunu)\s+(.+?)\s*(?:yaz|gönder|gonder|send)?$",
            )
            for pattern in raw_patterns:
                m = re.search(pattern, text, flags=re.IGNORECASE)
                if m:
                    msg = m.group(1).strip(" :,.")
                    break
        if msg:
            msg = re.sub(
                r"^(?:şunu|sunu|bunu|mesaj(?:ı|i)?|message|dm)\s+",
                "",
                msg,
                flags=re.IGNORECASE,
            ).strip(" :,.")
            msg = re.sub(
                r"\s+(?:de\s+ve\s+mesaj(?:ı|i)?|ve\s+mesaj(?:ı|i)?|de)$",
                "",
                msg,
                flags=re.IGNORECASE,
            ).strip(" :,.")
        if msg:
            msg = msg.strip()

        target = None
        mention = re.search(r"@([\w.-]{2,64})", text, flags=re.IGNORECASE)
        if mention:
            target = mention.group(1)
        if not target:
            m = re.search(
                r"(?:to|dm)\s+([\w.-]{2,64})",
                text,
                flags=re.IGNORECASE,
            )
            if m:
                target = m.group(1)
        if not target:
            m = re.search(
                r"([\w.-]{2,64})\s*(?:adlı|adli)?\s*(?:kişiye|kişisine|kisine|kisisine|kisiye)",
                text,
                flags=re.IGNORECASE,
            )
            if m:
                target = m.group(1)
        if not target:
            m = re.search(
                r"discord(?:da|de|ta|te)?\s+([\w.-]{2,64})",
                folded,
                flags=re.IGNORECASE,
            )
            if m:
                target = m.group(1)
        if target and fold_text(target) in {"adli", "uygulama", "uygulamada", "application", "app"}:
            target = None
        if not target or not msg:
            return None
        return target.strip("@ "), msg

    def _try_discord_flow(self, text: str) -> bool:
        channel_req = self._extract_discord_channel_request(text)
        if channel_req:
            server, channel, message = channel_req
            return self._run_discord_channel_message(server, channel, message)
        request = self._extract_discord_request(text)
        if not request:
            return False
        target, message = request
        try:
            if is_app_window_open("discord"):
                ensure_app_focus(
                    "discord",
                    settle=1.0,
                    wait_window=APP_LAUNCH_TIMEOUT,
                    ui_lang=self.ui_lang,
                )
            else:
                ok, _method = start_app_verified("discord", ui_lang=self.ui_lang)
                if not ok:
                    return False
                time.sleep(1.5)
                ensure_app_focus(
                    "discord",
                    settle=1.0,
                    wait_window=APP_LAUNCH_TIMEOUT,
                    ui_lang=self.ui_lang,
                )

            send_hotkey("ctrl k")
            time.sleep(0.5)
            type_text(target)
            time.sleep(0.8)
            send_hotkey("enter")
            time.sleep(1.4)

            type_text(message)
            time.sleep(0.1)
            send_hotkey("enter")
            show_status_popup(t(self.ui_lang, "command_popup_found"))
            self._speak_success()
            return True
        except Exception as exc:
            print(t(self.ui_lang, "command_failed", error=exc))
            show_status_popup(t(self.ui_lang, "command_popup_failed", error=exc))
            self._speak_fail()
            return True

    def _find_routine_request(self, text: str) -> tuple[str, str] | None:
        folded = fold_text(text or "")
        if not folded:
            return None
        trigger_terms = (
            "rutin",
            "routine",
            "mod",
            "mode",
            "baslat",
            "basla",
            "calistir",
            "calistir",
            "gec",
            "geç",
            "start",
            "run",
        )
        for name, entry in _routine_section().items():
            name_folded = fold_text(name)
            if not name_folded or name_folded not in folded:
                continue
            if any(term in folded for term in trigger_terms):
                val = entry.get("value") if isinstance(entry, dict) else entry
                if val:
                    return name, str(val)
        return None

    def _maybe_prepend_focus(self, text: str, actions: list[dict]) -> list[dict]:
        if not actions:
            return actions
        if not any(str(item.get("action", "")).startswith("gui_") for item in actions):
            return actions
        if any(item.get("action") == "focus" for item in actions):
            return actions
        text_folded = fold_text(text or "")
        app_name = None
        for name in APP_ALIASES.keys():
            if fold_text(name) in text_folded:
                app_name = name
                break
        if not app_name:
            return actions
        if not is_app_window_open(app_name):
            return actions
        steps = []
        steps.append(
            {
                "action": "focus",
                "value": app_name,
                "reason": "Bring app to front before GUI actions.",
                "critical": True,
            }
        )
        return steps + actions

    def _reorder_focus_after_start(self, actions: list[dict]) -> list[dict]:
        if not actions:
            return actions
        first_start: dict[str, int] = {}
        for idx, item in enumerate(actions):
            action = str(item.get("action", ""))
            value = str(item.get("value", "") or "")
            if action in ("start", "open") and value:
                name = canonical_app_name(value)
                if name and name not in first_start:
                    first_start[name] = idx
        if not first_start:
            return actions
        deferred: dict[str, list[dict]] = {}
        ordered: list[dict] = []
        for idx, item in enumerate(actions):
            action = str(item.get("action", ""))
            value = str(item.get("value", "") or "")
            if action == "focus" and value:
                name = canonical_app_name(value)
                if name in first_start and idx < first_start[name]:
                    deferred.setdefault(name, []).append(item)
                    continue
            ordered.append(item)
            if action in ("start", "open") and value:
                name = canonical_app_name(value)
                if name in deferred:
                    ordered.extend(deferred.pop(name))
        for remaining in deferred.values():
            ordered.extend(remaining)
        return ordered

    def _run_direct_actions(self, actions: list[dict], source_text: str) -> bool:
        if not actions:
            return False
        total = len([a for a in actions if (a.get("action") or "") not in ("none", "")])
        step_idx = 0
        for item in actions:
            action = item.get("action")
            value = item.get("value") or ""
            if not action or action == "none":
                continue
            step_idx += 1
            if self._needs_confirmation(action):
                if not self._await_confirmation(action, value):
                    print(t(self.ui_lang, "command_cancelled"))
                    show_status_popup(
                        t(self.ui_lang, "command_popup_failed", error="cancelled")
                    )
                    self._speak_fail()
                    return True
            show_agent_step_popup(
                step_idx,
                max(total, step_idx),
                str(action),
                str(value),
                ui_lang=self.ui_lang,
            )
            try:
                ok, fail_reason = execute_action(
                    action,
                    value,
                    tail_text=None,
                    ui_lang=self.ui_lang,
                    automation=self.automation,
                    web=self.web,
                )
            except Exception as exc:
                ok, fail_reason = False, str(exc)
            if ok:
                verification = verify_action(action, value, web=self.web, ui_lang=self.ui_lang)
                if not verification.get("ok", True):
                    ok = False
                    fail_reason = verification.get("reason", "verification_failed")
            if not ok:
                report_action_failure(
                    self.ui_lang,
                    fail_reason or "unknown",
                    value=value,
                    action=action,
                )
                self._speak_fail()
                return True
            if step_idx < total:
                time.sleep(max(0.0, AGENT_STEP_PAUSE_SEC))
        show_status_popup(t(self.ui_lang, "command_popup_done", action="done"))
        self._speak_success()
        return True

    def _handle_text_request(self, text: str, source_label: str, use_commands: bool):
        if use_commands:
            match = match_command(text, self.commands)
            if match:
                cmd, matched_phrase = match
                tail_text = extract_tail_text(text, matched_phrase)
                action = cmd.get("action")
                value = cmd.get("value")
                print(
                    t(
                        self.ui_lang,
                        "command_found",
                        phrase=matched_phrase,
                        action=action,
                        value=value,
                    )
                )
                show_status_popup(
                    t(
                        self.ui_lang,
                        "command_popup_running",
                        action=action,
                        value=value or "",
                    )
                )
                needs_map = action in {
                    "gui_click_text",
                    "gui_click_image",
                    "gui_click",
                    "gui_wait",
                    "gui_wait_text",
                    "gui_wait_image",
                    "gui_map",
                    "gui_click_index",
                    "web_open",
                    "web_click",
                    "web_type",
                    "web_press",
                    "web_wait",
                    "web_search",
                    "youtube_search",
                    "web_form_fill",
                }
                if needs_map:
                    self._start_auto_map()
                try:
                    ok, reason = execute_action(
                        action,
                        value,
                        tail_text,
                        self.ui_lang,
                        automation=self.automation,
                        web=self.web,
                    )
                    if not ok:
                        base = report_action_failure(
                            self.ui_lang,
                            reason or "unknown",
                            value=value,
                            action=action,
                        )
                        self._speak_fail()
                    else:
                        show_status_popup(t(self.ui_lang, "command_popup_found"))
                        self._speak_success()
                    return
                except Exception as exc:
                    report_action_failure(self.ui_lang, str(exc), action=action)
                    self._speak_fail()
                    return
                finally:
                    if needs_map:
                        self._stop_auto_map()

        # Weather shortcut: open default browser search directly.
        folded = fold_text(text or "")

        quick_actions = infer_quick_actions(text)
        if quick_actions:
            quick_actions = _fix_actions_from_text(text, quick_actions)
            if self._run_direct_actions(quick_actions, text):
                return

        structured = infer_structured_workflow(text)
        if structured:
            structured = _fix_actions_from_text(text, structured)
            if self._run_direct_actions(structured, text):
                return

        if "hava durumu" in folded or "weather" in folded:
            open_search(text)
            show_status_popup(t(self.ui_lang, "command_popup_found"))
            return

        # YouTube shortcut: search and open first non-ad result (Playwright unless browser requested).
        if any(key in folded for key in ("youtube", "youtu")) and any(
            key in folded
            for key in (
                "video",
                "izle",
                "watch",
                "aç",
                "ac",
                "ara",
                "search",
                "bul",
                "asmr",
            )
        ):
            query = (
                folded.replace("youtube", "")
                .replace("youtu", "")
                .replace("videosu", "")
                .replace("video", "")
                .replace("izle", "")
                .replace("watch", "")
                .replace("aç", "")
                .replace("ac", "")
                .replace("ara", "")
                .replace("search", "")
                .replace("bul", "")
                .replace("bana", "")
                .replace("lütfen", "")
                .strip()
            )
            if not query:
                query = text
            avoid_pw, browser = detect_browser_request(text)
            if avoid_pw:
                from urllib.parse import quote_plus

                clean_query = clean_youtube_query(query)
                ok = open_youtube_first_result(clean_query, browser=browser, ui_lang=self.ui_lang)
                if not ok:
                    url = f"https://www.youtube.com/results?search_query={quote_plus(clean_query or query)}"
                    open_url_in_browser(browser, url)
                show_status_popup(t(self.ui_lang, "command_popup_found"))
            else:
                self._start_auto_map()
                try:
                    self.web.youtube_search(query)
                    show_status_popup(t(self.ui_lang, "command_popup_found"))
                finally:
                    self._stop_auto_map()
            return

        routine = self._find_routine_request(text)
        if routine and self._llm_ready():
            name, routine_text = routine
            print(t(self.ui_lang, "routine_found", name=name))
            self._handle_llm_request(routine_text, source_label)
            return

        if self._try_form_flow(text):
            return

        if self._try_discord_flow(text):
            return

        handled = False
        if self._llm_ready():
            print(t(self.ui_lang, "llm_fallback"))
            handled = self._handle_llm_request(text, source_label)

        if not handled:
            print(t(self.ui_lang, "command_not_found"))
            show_status_popup(t(self.ui_lang, "command_popup_not_found", text=text))
            self._speak_fail()

    def toggle(self):
        with self.lock:
            if not self.recording:
                self._start_recording()
            else:
                self._stop_recording()

    def shutdown(self):
        self.cancel_event.set()
        self._stop_auto_map()
        self.job_queue.stop(timeout=15.0)
        try:
            self.web.close()
        except Exception:
            pass


def run_control_mode(ui_lang, transcriber, commands, tts=None, llm=None, vlm=None, automation=None):
    session = ControlSession(ui_lang, transcriber, commands, tts=tts, llm=llm, vlm=vlm, automation=automation)
    pressed = set()
    hotkey_active = {"state": False}
    stop_event = threading.Event()
    input_queue = queue.Queue()

    def is_ctrl(key):
        return key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r)

    def is_shift(key):
        return key in (
            keyboard.Key.shift,
            keyboard.Key.shift_l,
            keyboard.Key.shift_r,
        )

    def is_six(key):
        if isinstance(key, keyboard.KeyCode):
            if key.char in ("6", "^"):
                return True
            if key.vk == 0x36:
                return True
        return False

    def on_press(key):
        pressed.add(key)
        if is_six(key) and not hotkey_active["state"]:
            if any(is_ctrl(k) for k in pressed) and any(is_shift(k) for k in pressed):
                hotkey_active["state"] = True
                session.toggle()

    def on_release(key):
        pressed.discard(key)
        if is_six(key):
            hotkey_active["state"] = False

    def input_worker():
        while not stop_event.is_set():
            try:
                line = input()
            except (EOFError, KeyboardInterrupt):
                stop_event.set()
                break
            input_queue.put(line)

    print("\n" + t(ui_lang, "control_active"))
    session._print_active_models()
    print(t(ui_lang, "control_hotkey"))
    print(t(ui_lang, "control_background"))
    print(t(ui_lang, "control_queue"))
    print(t(ui_lang, "control_exit"))
    planner = session._planner()
    if planner and getattr(planner, "only_mode", False):
        print(t(ui_lang, "llm_only_tip"))
    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    input_thread = threading.Thread(target=input_worker, daemon=True)
    input_thread.start()
    try:
        while not stop_event.is_set():
            try:
                line = input_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            except KeyboardInterrupt:
                if session.cancel_current():
                    continue
                stop_event.set()
                break
            if session.handle_input_line(line):
                stop_event.set()
                break
    except KeyboardInterrupt:
        if not session.cancel_current():
            stop_event.set()
    finally:
        stop_event.set()
        listener.stop()
        session.shutdown()
