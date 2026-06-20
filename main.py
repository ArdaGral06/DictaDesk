import platform

from app_logging import setup_logging
from audio_io import ensure_dirs
from commands_manager import get_commands_for_lang, load_commands, manage_commands
from config import DEFAULT_UI_LANG, GUI_AUTOMATION_DEFAULT, WEB_AUTOMATION_DEFAULT
from control_mode import run_control_mode
from engine import choose_engine, stt_available
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


def choose_ui_language():
    choice = input(t(DEFAULT_UI_LANG, "choose_ui_language")).strip().lower()
    return safe_lang(choice) if choice else DEFAULT_UI_LANG


def run_settings(ui_lang, tts_manager, llm_manager, vlm_manager, automation):
    while True:
        status = tts_manager.status_text(ui_lang) if tts_manager else "-"
        llm_status = llm_manager.status_text(ui_lang) if llm_manager else "-"
        vlm_status = vlm_manager.status_text(ui_lang) if vlm_manager else "-"
        gui_status = t(ui_lang, "toggle_on") if automation.gui_enabled else t(ui_lang, "toggle_off")
        web_status = t(ui_lang, "toggle_on") if automation.web_enabled else t(ui_lang, "toggle_off")
        agent_mgr = llm_manager if llm_manager else None
        llm_only_status = (
            t(ui_lang, "llm_only_on")
            if (agent_mgr and getattr(agent_mgr, "only_mode", False))
            else t(ui_lang, "llm_only_off")
        )
        llm_delay = float(getattr(agent_mgr, "multi_delay", 0.0) or 0.0)
        print("\n" + t(ui_lang, "settings_title"))
        print(t(ui_lang, "settings_tts_status", status=status))
        print(t(ui_lang, "settings_llm_status", status=llm_status))
        print(t(ui_lang, "settings_vlm_status", status=vlm_status))
        print(t(ui_lang, "settings_gui_status", status=gui_status))
        print(t(ui_lang, "settings_web_status", status=web_status))
        print(t(ui_lang, "settings_llm_only_status", status=llm_only_status))
        print(t(ui_lang, "settings_llm_delay_status", seconds=llm_delay))
        print(t(ui_lang, "settings_budget_status", status=budget_status_text(ui_lang)))
        print(t(ui_lang, "settings_tts_toggle"))
        print(t(ui_lang, "settings_llm_toggle"))
        print(t(ui_lang, "settings_vlm_toggle"))
        print(t(ui_lang, "settings_gui_toggle"))
        print(t(ui_lang, "settings_web_toggle"))
        print(t(ui_lang, "settings_llm_only_toggle"))
        print(t(ui_lang, "settings_llm_delay_set"))
        print(t(ui_lang, "settings_memory"))
        print(t(ui_lang, "settings_budget_menu"))
        print(t(ui_lang, "settings_api_providers"))
        print(t(ui_lang, "settings_back"))
        choice = input(t(ui_lang, "menu_select")).strip()
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
    transcriber = choose_engine(ui_lang)
    tts = choose_tts(ui_lang)
    llm = choose_llm(ui_lang)
    vlm = choose_vlm(ui_lang)
    automation = AutomationSettings(
        gui_enabled=GUI_AUTOMATION_DEFAULT,
        web_enabled=WEB_AUTOMATION_DEFAULT,
    )
    commands_by_lang = load_commands()

    while True:
        print("\n" + t(ui_lang, "menu_title"))
        print(t(ui_lang, "menu_control"))
        print(t(ui_lang, "menu_test"))
        print(t(ui_lang, "menu_selfcheck"))
        print(t(ui_lang, "menu_manage"))
        print(t(ui_lang, "menu_settings"))
        print(t(ui_lang, "menu_exit"))
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
