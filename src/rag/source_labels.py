"""Canonical labels shared by RAG context formatting and citation checks."""
from __future__ import annotations

import re


_WHITESPACE_RE = re.compile(r"\s+")


def normalize_source_label(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", str(value or "").strip())


def format_source_label(name: str, heading_path: str = "") -> str:
    name = normalize_source_label(name)
    heading = normalize_source_label(heading_path)
    if not heading or heading == name:
        return name
    if name and heading.startswith(f"{name} /"):
        return heading
    return f"{name} / {heading}" if name else heading

