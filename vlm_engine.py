import base64
import json
import re
from pathlib import Path

import requests

from config import VLM_PROVIDERS_JSON, DEFAULT_UI_LANG, DEFAULT_VLM_MODEL
from api_provider_config import ensure_api_model
from api_budget import check_budget, record_budget_usage
from http_retry import post_with_retry
from i18n import t
from ui_terminal import print_wizard
from llm_engine import LLMManager, _extract_json
from secrets_store import get_entry, set_entry


def _image_to_data_url(image_path: str) -> str:
    path = Path(image_path)
    suffix = path.suffix.lower().lstrip(".")
    if suffix in ("jpg", "jpeg"):
        mime = "image/jpeg"
    elif suffix in ("webp",):
        mime = "image/webp"
    else:
        mime = "image/png"
    data = path.read_bytes()
    encoded = base64.b64encode(data).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def _parse_xy_from_text(text: str, width: int, height: int) -> tuple[int | None, int | None, str]:
    raw_reason = ""
    if not text:
        return None, None, raw_reason
    payload = _extract_json(text)
    if isinstance(payload, dict):
        if payload.get("not_found"):
            raw_reason = str(payload.get("reason", "not_found"))
            return None, None, raw_reason
        x_val = payload.get("x")
        y_val = payload.get("y")
        if x_val is not None and y_val is not None:
            try:
                x = float(x_val)
                y = float(y_val)
                if 0 < x <= 1 and 0 < y <= 1:
                    x = x * width
                    y = y * height
                x_i = int(round(x))
                y_i = int(round(y))
                if 0 <= x_i < width and 0 <= y_i < height:
                    return x_i, y_i, str(payload.get("reason", "")).strip()
            except Exception:
                pass

    nums = re.findall(r"-?\d+(?:\.\d+)?", text)
    if len(nums) >= 2:
        try:
            x = float(nums[0])
            y = float(nums[1])
            if 0 < x <= 1 and 0 < y <= 1:
                x = x * width
                y = y * height
            x_i = int(round(x))
            y_i = int(round(y))
            if 0 <= x_i < width and 0 <= y_i < height:
                return x_i, y_i, ""
        except Exception:
            pass
    return None, None, raw_reason


def _vlm_system_prompt() -> str:
    return (
        "You are a vision observer for a Windows desktop automation agent. "
        "Your only job is to describe the screenshot for the planner. "
        "Do not plan actions, do not execute actions, and do not decide the task order. "
        "Return JSON only with keys: visible_app, active_window, screen_summary, "
        "visible_texts, clickable_targets, warnings, suggested_targets. "
        "clickable_targets items may include label, type, approximate_position, region, nearby_text, and confidence. "
        "When the same label appears multiple times, list every occurrence separately with its region and purpose. "
        "For Discord, distinguish left DM list, center friend/search results, message input, and right activity/profile panels; activity/profile panels are usually informational, not DM targets. "
        "suggested_targets should be observations only, not commands."
    )


class ApiVLM:
    def __init__(self, provider: dict, api_key: str, model: str):
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.last_error = ""

    def _headers(self) -> dict:
        headers_tpl = self.provider.get("headers", {})
        headers = {}
        for k, v in headers_tpl.items():
            headers[k] = v.format(api_key=self.api_key)
        return headers

    def _post(self, payload: dict) -> str:
        self.last_error = ""
        endpoint = str(self.provider.get("endpoint", "")).strip()
        if not endpoint or not self.api_key:
            return ""
        allowed, block_msg = check_budget("vlm", DEFAULT_UI_LANG)
        if not allowed:
            self.last_error = block_msg or "budget_blocked"
            return ""
        timeout = int(self.provider.get("timeout_sec", 60))
        try:
            resp = post_with_retry(
                endpoint,
                headers=self._headers(),
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            record_budget_usage("vlm")
        except Exception as exc:
            self.last_error = str(exc)
            return ""
        path = self.provider.get("response_path", [])
        current = data
        for key in path:
            try:
                if isinstance(key, int):
                    current = current[key]
                else:
                    current = current.get(key)
            except Exception:
                return ""
        return current if isinstance(current, str) else ""

    def generate(
        self,
        text: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        raw_user: bool = False,
    ) -> str:
        user_text = text if raw_user else text
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt or _vlm_system_prompt()},
                {"role": "user", "content": user_text},
            ],
            "temperature": 0.2 if temperature is None else temperature,
        }
        return self._post(payload)

    def generate_with_image(
        self,
        text: str,
        image_path: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
    ) -> str:
        image_url = _image_to_data_url(image_path)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt or _vlm_system_prompt()},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
            "temperature": 0.2 if temperature is None else temperature,
        }
        return self._post(payload)


class VLMManager(LLMManager):
    def __init__(self, vlm, label: str, enabled: bool = True):
        super().__init__(vlm, label, enabled)

    def locate_click(
        self,
        instruction: str,
        image_path: str,
        ui_lang: str | None = None,
        goal: str | None = None,
    ) -> tuple[int | None, int | None, str, str]:
        if not self.enabled or not self.llm:
            return None, None, "disabled", ""

        from PIL import Image

        try:
            with Image.open(image_path) as img:
                width, height = img.size
        except Exception:
            width, height = 0, 0

        goal_text = goal.strip() if goal else ""
        target_text = (instruction or "").strip()
        if goal_text and target_text:
            prompt = (
                f"Goal: {goal_text}\nTarget: {target_text}\n"
                f"Image size: {width}x{height}\n"
                "Return JSON only."
            )
        elif target_text:
            prompt = (
                f"Target: {target_text}\nImage size: {width}x{height}\n"
                "Return JSON only."
            )
        else:
            prompt = (
                f"Goal: {goal_text}\nImage size: {width}x{height}\nReturn JSON only."
            )

        raw = self.llm.generate_with_image(prompt, image_path, system_prompt=_vlm_system_prompt())
        x, y, reason = _parse_xy_from_text(raw, width or 1, height or 1)
        if x is None or y is None:
            return None, None, reason or "not_found", raw
        return x, y, reason, raw

    def observe_screen(
        self,
        image_path: str,
        goal: str | None = None,
        ocr_items: list[dict] | None = None,
    ) -> tuple[dict | None, str]:
        if not self.enabled or not self.llm:
            return None, ""
        ocr_preview = []
        for item in (ocr_items or [])[:80]:
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            ocr_preview.append(
                {
                    "text": text,
                    "left": item.get("left"),
                    "top": item.get("top"),
                    "width": item.get("width"),
                    "height": item.get("height"),
                }
            )
        prompt = {
            "goal": goal or "",
            "instruction": (
                "Describe what is visible in the screenshot for the LLM planner. "
                "Use OCR/map data as hints, but rely on the image when OCR is noisy. "
                "Return JSON only and do not create action steps."
            ),
            "ocr_map_preview": ocr_preview,
        }
        raw = self.llm.generate_with_image(
            json.dumps(prompt, ensure_ascii=False),
            image_path,
            system_prompt=_vlm_system_prompt(),
            temperature=0.0,
        )
        payload = _extract_json(raw)
        if isinstance(payload, dict):
            return payload, raw
        return None, raw


def load_vlm_providers():
    if not VLM_PROVIDERS_JSON.exists():
        return []
    data = json.loads(VLM_PROVIDERS_JSON.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("providers"), list):
        return data["providers"]
    if isinstance(data, list):
        return data
    return []


def choose_vlm(ui_lang, prefs_out: dict | None = None):
    while True:
        print_wizard(
            ui_lang,
            title_key="vlm_title",
            subtitle_key="vlm_subtitle",
            options=[
                ("1", "vlm_off_title", "vlm_off_desc"),
                ("2", "vlm_api_title", "vlm_api_desc"),
            ],
        )
        choice = input(t(ui_lang, "vlm_select")).strip().lower()

        if choice in ("1", "off", ""):
            if prefs_out is not None:
                prefs_out["vlm"] = "off"
                prefs_out.pop("vlm_provider", None)
            return VLMManager(None, t(ui_lang, "vlm_label_off"), enabled=False)

        if choice in ("2", "api"):
            providers = load_vlm_providers()
            if not providers:
                print(t(ui_lang, "vlm_provider_missing"))
                return VLMManager(None, t(ui_lang, "vlm_label_off"), enabled=False)

            print("\n" + t(ui_lang, "vlm_provider_title"))
            for i, provider in enumerate(providers, start=1):
                label = provider.get("label") or provider.get("id", f"provider_{i}")
                print(f"{i}) {label}")

            select = input(t(ui_lang, "vlm_provider_select")).strip().lower()
            provider = None
            if select.isdigit():
                idx = int(select) - 1
                if 0 <= idx < len(providers):
                    provider = providers[idx]
            else:
                for item in providers:
                    if item.get("id", "").lower() == select:
                        provider = item
                        break
            if provider is None:
                provider = providers[0]

            provider_id = provider.get("id", "provider")
            saved_vlm = get_entry("vlm", provider_id)
            saved_llm = get_entry("llm", provider_id)
            saved_key = None
            if isinstance(saved_vlm, dict):
                saved_key = saved_vlm.get("api_key")
            if not saved_key and isinstance(saved_llm, dict):
                saved_key = saved_llm.get("api_key")

            if saved_key:
                api_key = input(t(ui_lang, "vlm_api_key_prompt_saved")).strip()
                if not api_key:
                    api_key = saved_key
            else:
                api_key = input(t(ui_lang, "vlm_api_key_prompt")).strip()
            if not api_key:
                return VLMManager(None, t(ui_lang, "vlm_label_off"), enabled=False)

            model = ensure_api_model(
                "vlm",
                provider_id,
                provider,
                saved_vlm if isinstance(saved_vlm, dict) else {},
                default=DEFAULT_VLM_MODEL,
                api_key=api_key,
                ui_lang=ui_lang,
            )
            model_hint = provider.get("model_hint", "") or DEFAULT_VLM_MODEL
            model_default = model or model_hint
            model = input(t(ui_lang, "vlm_model_prompt", default=model_default)).strip()
            if not model:
                model = model_default

            set_entry("vlm", provider_id, {"api_key": api_key, "model": model})
            print(t(ui_lang, "api_saved"))
            if prefs_out is not None:
                prefs_out["vlm"] = "api"
                prefs_out["vlm_provider"] = provider_id
            label = f"{t(ui_lang, 'vlm_label_api')} ({provider.get('label', provider_id)})"
            return VLMManager(ApiVLM(provider=provider, api_key=api_key, model=model), label, enabled=True)

        print(t(ui_lang, "invalid_choice"))
