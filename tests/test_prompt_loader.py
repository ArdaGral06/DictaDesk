from llm_engine import _agent_system_prompt, _router_system_prompt
from prompt_loader import load_prompt, render_prompt


def test_prompt_files_exist():
    for name in (
        "router_system.txt",
        "agent_system.txt",
        "synonym_guide.txt",
        "coding_guide.txt",
    ):
        text = load_prompt(name)
        assert text.strip()


def test_router_prompt_renders_without_placeholders():
    prompt = _router_system_prompt()
    assert "{{" not in prompt
    assert "command router" in prompt.lower()


def test_agent_prompt_renders_without_placeholders():
    prompt = _agent_system_prompt(coding=True)
    assert "{{" not in prompt
    assert "planning agent" in prompt.lower()


def test_render_prompt_substitutes():
    out = render_prompt("synonym_guide.txt", dummy="")
    assert "SYNONYM" in out
