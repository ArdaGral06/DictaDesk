from i18n import fail_reason_text, t
from ui_popup import show_status_popup

KNOWN_FAILURES = {
    "missing",
    "gui_disabled",
    "web_disabled",
    "app_not_open",
    "focus_failed",
    "map_empty",
    "map_index",
    "no_text",
    "captcha_required",
    "routine_missing",
    "blocked",
    "verification_failed",
    "file_path_missing",
    "file_not_found",
    "file_missing",
    "unsupported_code_type",
    "run_code_failed",
    "run_code_not_executed",
    "path_not_allowed",
    "shell_blocked",
    "app_window_missing",
    "app_not_focused",
    "app_still_open",
    "path_missing",
    "dir_missing",
    "youtube_video_not_opened",
    "web_action_failed",
    "cancelled",
    "unknown",
    "gui_not_executed",
    "gui_action_failed",
    "gui_image_not_found",
}


def failure_console_message(ui_lang: str, fail_reason: str, *, value: str | None = None) -> str:
    reason = str(fail_reason or "unknown")
    base = reason.split(":")[0].lower()
    if base == "app_not_open" and value:
        return t(ui_lang, "app_start_failed", name=value)
    if base == "focus_failed" and value:
        return t(ui_lang, "focus_failed", name=value)
    if base == "missing":
        return t(ui_lang, "command_missing")
    if base == "gui_disabled":
        return t(ui_lang, "automation_gui_disabled")
    if base == "web_disabled":
        return t(ui_lang, "automation_web_disabled")
    if base == "map_empty":
        return t(ui_lang, "gui_map_empty")
    if base == "map_index":
        return t(ui_lang, "gui_map_index")
    if base == "no_text":
        return t(ui_lang, "ocr_empty")
    if base == "captcha_required":
        return t(ui_lang, "captcha_required")
    if base == "routine_missing":
        return t(ui_lang, "command_failed", error=fail_reason_text(ui_lang, reason))
    if base == "blocked":
        return t(ui_lang, "open_blocked")
    if base == "unknown":
        return t(ui_lang, "unknown_action", action=value or "?")
    return t(ui_lang, "command_failed", error=fail_reason_text(ui_lang, reason))


def report_action_failure(
    ui_lang: str,
    fail_reason: str,
    *,
    value: str | None = None,
    action: str | None = None,
    show_popup: bool = True,
) -> str:
    reason = str(fail_reason or "unknown")
    base = reason.split(":")[0].lower()
    message = failure_console_message(
        ui_lang,
        reason,
        value=value if value is not None else action,
    )
    print(message)
    if show_popup:
        show_status_popup(
            t(
                ui_lang,
                "command_popup_failed",
                error=fail_reason_text(ui_lang, reason),
            )
        )
    return base


def is_known_failure(fail_reason: str) -> bool:
    base = str(fail_reason or "").split(":")[0].lower()
    return base in KNOWN_FAILURES or base.startswith("run_code_failed")
