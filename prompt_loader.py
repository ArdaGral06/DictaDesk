"""Load LLM prompt templates from prompts/ ({{name}} placeholders)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


@lru_cache(maxsize=32)
def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"prompt_missing: {path}")
    return path.read_text(encoding="utf-8")


def render_prompt(name: str, **values: str) -> str:
    text = load_prompt(name)
    for key, val in values.items():
        text = text.replace("{{" + key + "}}", val or "")
    return text
