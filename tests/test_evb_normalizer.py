from __future__ import annotations

import pytest

from src.huiji_rag.normalizer import (
    ascii_filename_key,
    expected_voice_filename,
    normalize_language,
    validate_safe_id,
)


def test_validate_safe_id_rejects_separator_colon_dot_and_controls():
    for unsafe in ("", ".", "..", "evb/gate", "evb\\gate", "evb:gate", "evb\x00gate", "evb\ngate"):
        with pytest.raises(ValueError):
            validate_safe_id(unsafe, "build_version")

    assert validate_safe_id("evb-gate_20260711", "build_version") == "evb-gate_20260711"


def test_expected_voice_filename_uses_exact_prefix_nfc_and_mp3():
    assert expected_voice_filename("Cafe\u0301", "en-us") == "En_Caf\u00e9.mp3"
    with pytest.raises(ValueError):
        expected_voice_filename("unsafe.mp3", "en")


def test_ascii_filename_key_does_not_unicode_casefold():
    assert ascii_filename_key("En_CAFE\u0301.MP3") == "en_caf\u00c9.mp3"
    assert ascii_filename_key("\u0130.MP3") == "\u0130.mp3"


def test_zh_hant_aliases_only_use_tw():
    for alias in ("tw", "zh-tw", "zh_hant", "zh-hant"):
        assert normalize_language(alias) == ("zh-hant", "Tw")
        assert expected_voice_filename("event", alias) == "Tw_event.mp3"
