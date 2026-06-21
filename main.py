import platform

from app_logging import setup_logging
from audio_io import ensure_dirs
from commands_manager import get_commands_for_lang, load_commands, manage_commands
from config import DEFAULT_UI_LANG, GUI_AUTOMATION_DEFAULT, WEB_AUTOMATION_DEFAULT
from control_mode import run_control_mode
from engine import choose_engine, get_stt_label, stt_available
from i18n import safe_lang, t
from self_check import run_self_check
from test import run_test_mode
from tts_engine import choose_tts, require_piper
from llm_engine import choose_llm
from vlm_engine import choose_vlm
from automation_settings import AutomationSettings
from agent_memory import run_memory_menu
from api_budget import budget_status_text, run_budget_menu
from api_provider_config import run_provider_info_menu
from secrets_store import load_secrets
from ui_terminal import print_banner, print_compact_status, print_menu, print_option, print_section
from ui_popup import show_status_popup


def choose_ui_language():
    choice = input(t(DEFAULT_UI_LANG, "choose_ui_language")).strip().lower()
    return safe_lang(choice) if choice else DEFAULT_UI_LANG


def _print_setup_summary(ui_lang, transcriber, tts, llm, vlm):
    print_banner(
        t(ui_lang, "setup_complete_title"),
        t(ui_lang, "setup_complete_subtitle"),
    )
    print_compact_status(
        ui_lang,
        [
            (t(ui_lang, "setup_stt_label"), get_stt_label(transcriber)),
            (t(ui_lang, "setup_tts_label"), tts.status_text(ui_lang) if tts else "-"),
            (t(ui_lang, "setup_agent_label"), llm.status_text(ui_lang) if llm else "-"),
            (t(ui_lang, "setup_vlm_label"), vlm.status_text(ui_lang) if vlm else "-"),
        ],
    )


def _print_main_menu(ui_lang):
    print_menu(
        ui_lang,
        title_key="menu_title",
        subtitle_key="menu_subtitle",
        items=[
            {"num": "1", "title_key": "menu_control_title", "desc_key": "menu_control_desc"},
            {"num": "2", "title_key": "menu_test_title", "desc_key": "menu_test_desc"},
            {"num": "3", "title_key": "menu_selfcheck_title", "desc_key": "menu_selfcheck_desc"},
            {"num": "4", "title_key": "menu_manage_title", "desc_key": "menu_manage_desc"},
            {"num": "5", "title_key": "menu_settings_title", "desc_key": "menu_settings_desc"},
            {"num": "6", "title_key": "menu_exit_title", "desc_key": "menu_exit_desc"},
        ],
    )


def _print_settings_menu(ui_lang, tts_manager, llm_manager, vlm_manager, automation):
    agent_mgr = llm_manager if llm_manager else None
    llm_only_status = (
        t(ui_lang, "llm_only_on")
        if (agent_mgr and getattr(agent_mgr, "only_mode", False))
        else t(ui_lang, "llm_only_off")
    )
    llm_delay = float(getattr(agent_mgr, "multi_delay", 0.0) or 0.0)

    print_menu(
        ui_lang,
        title_key="settings_title",
        subtitle_key="settings_subtitle",
        items=[],
    )
    print_compact_status(
        ui_lang,
        [
            (t(ui_lang, "status_col_tts"), tts_manager.status_text(ui_lang) if tts_manager else "-"),
            (t(ui_lang, "status_col_agent"), llm_manager.status_text(ui_lang) if llm_manager else "-"),
            (t(ui_lang, "status_col_vlm"), vlm_manager.status_text(ui_lang) if vlm_manager else "-"),
            (
                t(ui_lang, "settings_gui_title"),
                t(ui_lang, "toggle_on") if automation.gui_enabled else t(ui_lang, "toggle_off"),
            ),
            (
                t(ui_lang, "settings_web_title"),
                t(ui_lang, "toggle_on") if automation.web_enabled else t(ui_lang, "toggle_off"),
            ),
            (t(ui_lang, "settings_llm_only_title"), llm_only_status),
            (t(ui_lang, "settings_delay_title"), f"{llm_delay:.2f}s"),
            (t(ui_lang, "settings_budget_title"), budget_status_text(ui_lang)),
        ],
    )

    print_section(t(ui_lang, "settings_section_ai"))
    for num, title_key, desc_key in (
        ("1", "settings_tts_title", "settings_tts_desc"),
        ("2", "settings_llm_title", "settings_llm_desc"),
        ("3", "settings_vlm_title", "settings_vlm_desc"),
        ("6", "settings_llm_only_title", "settings_llm_only_desc"),
    ):
        print_option(num, t(ui_lang, title_key), t(ui_lang, desc_key))

    print_section(t(ui_lang, "settings_section_automation"))
    for num, title_key, desc_key in (
        ("4", "settings_gui_title", "settings_gui_desc"),
        ("5", "settings_web_title", "settings_web_desc"),
        ("7", "settings_delay_title", "settings_delay_desc"),
    ):
        print_option(num, t(ui_lang, title_key), t(ui_lang, desc_key))

    print_section(t(ui_lang, "settings_section_advanced"))
    for num, title_key, desc_key in (
        ("8", "settings_memory_title", "settings_memory_desc"),
        ("9", "settings_budget_title", "settings_budget_desc"),
        ("10", "settings_api_title", "settings_api_desc"),
        ("11", "settings_back_title", "settings_back_desc"),
    ):
        print_option(num, t(ui_lang, title_key), t(ui_lang, desc_key))


def run_settings(ui_lang, tts_manager, llm_manager, vlm_manager, automation):
    while True:
        _print_settings_menu(ui_lang, tts_manager, llm_manager, vlm_manager, automation)
        choice = input(t(ui_lang, "menu_select")).strip()
        agent_mgr = llm_manager if llm_manager else None
        if choice == "1":
            if tts_manager:
                tts_manager.toggle()
                print(
                    t(
                        ui_lang,
                        "settings_updated",
                        status=tts_manager.status_text(ui_lang),
                    )
                )
        elif choice == "2":
            if llm_manager:
                llm_manager.toggle()
                print(
                    t(
                        ui_lang,
                        "settings_updated",
                        status=llm_manager.status_text(ui_lang),
                    )
                )
        elif choice == "3":
            if vlm_manager:
                vlm_manager.toggle()
                print(
                    t(
                        ui_lang,
                        "settings_updated",
                        status=vlm_manager.status_text(ui_lang),
                    )
                )
        elif choice == "4":
            automation.toggle_gui()
            status = t(ui_lang, "toggle_on") if automation.gui_enabled else t(ui_lang, "toggle_off")
            print(t(ui_lang, "settings_updated", status=status))
        elif choice == "5":
            automation.toggle_web()
            status = t(ui_lang, "toggle_on") if automation.web_enabled else t(ui_lang, "toggle_off")
            print(t(ui_lang, "settings_updated", status=status))
        elif choice == "6":
            if agent_mgr:
                agent_mgr.toggle_only()
                status = (
                    t(ui_lang, "llm_only_on")
                    if agent_mgr.only_mode
                    else t(ui_lang, "llm_only_off")
                )
                print(t(ui_lang, "settings_updated", status=status))
                if agent_mgr.only_mode:
                    print(t(ui_lang, "llm_only_tip"))
        elif choice == "7":
            if agent_mgr:
                raw = input(t(ui_lang, "settings_delay_prompt")).strip()
                if raw:
                    try:
                        agent_mgr.multi_delay = max(0.0, float(raw))
                        print(
                            t(
                                ui_lang,
                                "settings_delay_updated",
                                seconds=agent_mgr.multi_delay,
                            )
                        )
                    except ValueError:
                        print(t(ui_lang, "settings_delay_invalid"))
        elif choice == "8":
            run_memory_menu(ui_lang)
        elif choice == "9":
            run_budget_menu(ui_lang)
        elif choice == "10":
            run_provider_info_menu(ui_lang)
        elif choice == "11":
            break


def main():
    setup_logging()
    ui_lang = choose_ui_language()
    if platform.system().lower() != "windows":
        print(t(ui_lang, "unsupported_os", os=platform.system()))
        return
    ensure_dirs()
    load_secrets()
    if not stt_available(ui_lang):
        print(t(ui_lang, "stt_missing"))
        return
    if not require_piper(ui_lang):
        return

    print_banner(t(ui_lang, "menu_title"), t(ui_lang, "setup_wizard_intro"))

    from startup_prefs import (
        apply_startup_prefs,
        ask_reuse_prefs,
        load_prefs,
        save_prefs,
    )

    saved_prefs = load_prefs()
    prefs_out: dict = {}
    if saved_prefs and ask_reuse_prefs(ui_lang, saved_prefs):
        transcriber, tts, llm, vlm = apply_startup_prefs(ui_lang, saved_prefs)
    else:
        transcriber = choose_engine(ui_lang, prefs_out)
        tts = choose_tts(ui_lang, prefs_out)
        llm = choose_llm(ui_lang, prefs_out)
        vlm = choose_vlm(ui_lang, prefs_out)
        if prefs_out:
            save_prefs(prefs_out)
    automation = AutomationSettings(
        gui_enabled=GUI_AUTOMATION_DEFAULT,
        web_enabled=WEB_AUTOMATION_DEFAULT,
    )
    commands_by_lang = load_commands()

    _print_setup_summary(ui_lang, transcriber, tts, llm, vlm)
    show_status_popup(
        t(ui_lang, "setup_complete_subtitle"),
        title=t(ui_lang, "setup_complete_title"),
    )

    while True:
        _print_main_menu(ui_lang)
        choice = input(t(ui_lang, "menu_select")).strip()

        if choice == "1":
            commands = get_commands_for_lang(commands_by_lang, ui_lang)
            run_control_mode(ui_lang, transcriber, commands, tts, llm, vlm, automation)
        elif choice == "2":
            run_test_mode(ui_lang, transcriber, tts)
        elif choice == "3":
            run_self_check(ui_lang)
        elif choice == "4":
            manage_commands(ui_lang, commands_by_lang)
        elif choice == "5":
            run_settings(ui_lang, tts, llm, vlm, automation)
        elif choice == "6":
            from web_automation import close_all_web_automation

            close_all_web_automation()
            break
        else:
            print(t(ui_lang, "invalid_choice"))


if __name__ == "__main__":
    main()
