"""Readable terminal menus — titles, descriptions, grouped sections."""

from __future__ import annotations

from i18n import t

_WIDTH = 64
_INDENT = "   "


def print_rule(char: str = "-") -> None:
    print(char * _WIDTH)


def print_blank() -> None:
    print()


def print_banner(title: str, subtitle: str | None = None) -> None:
    print_blank()
    print_rule("=")
    print(title.strip())
    if subtitle:
        print(subtitle.strip())
    print_rule("=")


def print_section(title: str) -> None:
    print_blank()
    print(f"  {title.strip()}")
    print_rule("-",)


def print_option(
    number: str,
    title: str,
    description: str | None = None,
    *,
    status: str | None = None,
) -> None:
    line = f"  {number}) {title.strip()}"
    if status:
        line += f"  [{status}]"
    print(line)
    if description:
        for part in description.strip().split("\n"):
            if part.strip():
                print(f"{_INDENT}{part.strip()}")


def print_bullet(text: str) -> None:
    print(f"  • {text.strip()}")


def print_status_row(label: str, value: str) -> None:
    print(f"  {label}: {value}")


def print_compact_status(ui_lang: str, rows: list[tuple[str, str]]) -> None:
    print_section(t(ui_lang, "ui_status_heading"))
    for label, value in rows:
        print_status_row(label, value)


def print_menu(
    ui_lang: str,
    *,
    title_key: str,
    subtitle_key: str | None = None,
    items: list[dict],
) -> None:
    """items: {num, title_key, desc_key?, status?}"""
    subtitle = t(ui_lang, subtitle_key) if subtitle_key else None
    print_banner(t(ui_lang, title_key), subtitle)
    for item in items:
        desc_key = item.get("desc_key")
        print_option(
            item["num"],
            t(ui_lang, item["title_key"]),
            t(ui_lang, desc_key) if desc_key else None,
            status=item.get("status"),
        )
    print_blank()


def print_wizard(
    ui_lang: str,
    *,
    title_key: str,
    subtitle_key: str,
    options: list[tuple[str, str, str]],
) -> None:
    """options: (number, title_key, desc_key)"""
    print_banner(t(ui_lang, title_key), t(ui_lang, subtitle_key))
    for num, title_key, desc_key in options:
        print_option(num, t(ui_lang, title_key), t(ui_lang, desc_key))
    print_blank()


def print_help_box(ui_lang: str, title_key: str, bullet_keys: list[str]) -> None:
    print_section(t(ui_lang, title_key))
    for key in bullet_keys:
        print_bullet(t(ui_lang, key))
