"""One-off helper to refresh prompt templates from in-code strings (dev use)."""
from pathlib import Path

import llm_engine as le
from actions_manifest import action_summary_for_prompt
from agent_memory import format_memory_for_prompt
from prompt_loader import load_prompt


def _router_os_hint() -> str:
    return (
        "This assistant is Windows-only. Prefer app names like 'File Explorer', "
        "'Notepad', and use 'explorer' for the file manager. "
        "If the user says 'Finder', treat it as File Explorer."
    )


def _agent_os_hint() -> str:
    return (
        "Windows-only. Windows apps: File Explorer, Notepad. "
        "Treat 'Finder' as File Explorer."
    )


if __name__ == "__main__":
    router = le._router_system_prompt()
    for old, new in [
        (le._allowed_actions_text(), "{{allowed_actions}}"),
        (le._os_label(), "{{os_name}}"),
        (_router_os_hint(), "{{os_hint}}"),
        (load_prompt("synonym_guide.txt"), "{{synonym_guide}}"),
        (action_summary_for_prompt(), "{{manifest}}"),
    ]:
        router = router.replace(old, new, 1)
    mem = format_memory_for_prompt()
    if mem:
        router = router.replace("\n" + mem, "{{memory_block}}", 1)
    else:
        router = router.rstrip() + "\n{{memory_block}}"
    (PROMPTS / "router_system.txt").write_text(router, encoding="utf-8")

    agent = le._agent_system_prompt(coding=True)
    for old, new in [
        ("max 8", "{{step_limit}}"),
        (le._allowed_actions_text(), "{{allowed_actions}}"),
        (le._os_label(), "{{os_name}}"),
        (_agent_os_hint(), "{{os_hint}}"),
        (load_prompt("synonym_guide.txt"), "{{synonym_guide}}"),
        ("\n" + load_prompt("coding_guide.txt") + "\n", "{{coding_block}}"),
        (action_summary_for_prompt(), "{{manifest}}"),
    ]:
        agent = agent.replace(old, new, 1)
    mem = format_memory_for_prompt()
    if mem:
        agent = agent.replace("\n" + mem, "{{memory_block}}", 1)
    else:
        agent = agent.rstrip() + "\n{{memory_block}}"
    (PROMPTS / "agent_system.txt").write_text(agent, encoding="utf-8")
    print("wrote router_system.txt and agent_system.txt")
