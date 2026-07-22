"""Strict normalization helpers for EventName voice binding."""
from __future__ import annotations

import re
import unicodedata


LANGUAGE_ALIASES: dict[str, tuple[str, str]] = {
    "zh": ("zh", "Zh"),
    "cn": ("zh", "Zh"),
    "zh-cn": ("zh", "Zh"),
    "en": ("en", "En"),
    "en-us": ("en", "En"),
    "jp": ("jp", "Jp"),
    "ja": ("jp", "Jp"),
    "ja-jp": ("jp", "Jp"),
    "kr": ("kr", "Kr"),
    "ko": ("kr", "Kr"),
    "ko-kr": ("kr", "Kr"),
    "tw": ("zh-hant", "Tw"),
    "zh-tw": ("zh-hant", "Tw"),
    "zh_hant": ("zh-hant", "Tw"),
    "zh-hant": ("zh-hant", "Tw"),
}

_SAFE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")


def validate_safe_id(value: str, field: str) -> str:
    """Validate an ASCII identifier that is safe to use as one path component."""
    if not isinstance(value, str) or not _SAFE_ID_RE.fullmatch(value):
        raise ValueError(f"{field} must be a safe identifier")
    return value


def validate_event_name(value: str) -> str:
    """Validate raw eventName as a single, extension-free basename."""
    if not isinstance(value, str) or not value:
        raise ValueError("event_name must be a non-empty basename")
    if value in {".", ".."} or ".." in value:
        raise ValueError("event_name must not contain a dot segment")
    if "/" in value or "\\" in value:
        raise ValueError("event_name must not contain a path separator")
    if value.casefold().endswith(".mp3"):
        raise ValueError("event_name must not include an mp3 extension")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("event_name must not contain control characters")
    return value


def normalize_language(value: str) -> tuple[str, str]:
    if not isinstance(value, str):
        raise ValueError("language must be a string")
    alias = value.strip().lower()
    try:
        return LANGUAGE_ALIASES[alias]
    except KeyError as error:
        raise ValueError(f"unsupported language alias: {value}") from error


def expected_voice_filename(raw_event_name: str, language: str) -> str:
    _canonical, prefix = normalize_language(language)
    event_name = validate_event_name(unicodedata.normalize("NFC", raw_event_name))
    return f"{prefix}_{event_name}.mp3"


def ascii_filename_key(basename: str) -> str:
    normalized = unicodedata.normalize("NFC", basename)
    return "".join(
        chr(ord(character) + 32) if "A" <= character <= "Z" else character
        for character in normalized
    )
