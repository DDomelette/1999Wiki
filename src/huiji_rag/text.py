"""Text cleanup helpers for Huiji wiki content."""
from __future__ import annotations

import html
import re


def clean_huiji_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\[\[([^|\]]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return compact_lines(text)


def compact_lines(value: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in value.splitlines()]
    return "\n".join(line for line in lines if line)


def short_summary(value: str, max_chars: int = 240) -> str:
    text = compact_lines(value)
    if len(text) <= max_chars:
        return text
    match = re.search(r"[。！？.!?]", text[max_chars:])
    if match and match.end() <= 40:
        return text[: max_chars + match.end()].rstrip()
    return text[:max_chars].rstrip()

