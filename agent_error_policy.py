ERROR_RETRY = "retry"
ERROR_SKIP = "skip"
ERROR_REPLAN = "replan"
ERROR_ABORT = "abort"


def decide_error_policy(
    action: str | None,
    fail_reason: str | None,
    critical: bool,
    retry_count: int,
    replan_attempts: int,
) -> str:
    if not critical:
        return ERROR_SKIP
    reason = str(fail_reason or "").lower()
    action_name = str(action or "").lower()
    if reason in {"missing", "gui_disabled", "web_disabled", "blocked", "captcha_required"}:
        return ERROR_ABORT
    if action_name == "close" and reason == "app_still_open" and retry_count < 1:
        return ERROR_RETRY
    if replan_attempts >= 2:
        return ERROR_ABORT
    transient = any(
        token in reason
        for token in (
            "timeout",
            "temporarily",
            "temporary",
            "busy",
            "locked",
            "file in use",
            "network",
            "connection",
        )
    )
    no_blind_retry = {
        "start",
        "open",
        "focus",
        "close",
        "delete",
        "cmd",
        "powershell",
        "shutdown",
        "restart",
        "sleep",
    }
    if transient and retry_count < 1 and action_name not in no_blind_retry:
        return ERROR_RETRY
    return ERROR_REPLAN
