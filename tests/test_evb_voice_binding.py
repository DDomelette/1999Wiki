from __future__ import annotations

import pytest

from src.huiji_rag.media import media_id_for_sha1
from src.huiji_rag.models import BindingStatus, ResourceRow, VoiceSourceRow
from src.huiji_rag.voice_binding import bind_voice_row, index_voice_resources


def _source(event_name: str, language: str = "en", **kwargs: str) -> VoiceSourceRow:
    return VoiceSourceRow(event_name=event_name, language=language, **kwargs)


def _resource(
    filename: str,
    language: str = "en",
    sha1: str = "a" * 40,
    sha256: str = "b" * 64,
    **kwargs: str,
) -> ResourceRow:
    return ResourceRow(
        filename=filename,
        language=language,
        sha1=sha1,
        sha256=sha256,
        **kwargs,
    )


@pytest.mark.parametrize(
    ("source", "resources", "expected"),
    [
        (_source("WakeUp", "en-us"), [_resource("EN_wAkEuP.MP3")], "En_WakeUp.mp3"),
        (_source("Awake", "jp"), [_resource("jP_AWAKE.mp3", "ja")], "Jp_Awake.mp3"),
    ],
)
def test_binding_uses_exact_ascii_insensitive_full_basename(source, resources, expected):
    record = bind_voice_row(source, index_voice_resources(resources))

    assert record.status is BindingStatus.EXACT
    assert record.expected_filename == expected
    assert record.matches == tuple(resources)


def test_duplicate_matching_resources_with_same_sha256_are_exact():
    resources = [
        _resource("En_WakeUp.mp3"),
        _resource("en_wakeup.mp3"),
    ]

    record = bind_voice_row(_source("WakeUp"), index_voice_resources(resources))

    assert record.status is BindingStatus.EXACT
    assert record.matches == tuple(resources)


@pytest.mark.parametrize(
    "resource",
    [
        _resource("En_WakeUp.mp3"),
        _resource("ignored.mp3", title="En_WakeIp.mp3"),
        _resource("En_TheWakeUp.mp3"),
        _resource("En_WakeUp.mp3.bak"),
        _resource("archive_En_WakeUp.mp3"),
        _resource("En_WakeUp.wav"),
        _resource("En_Wake\u0130p.mp3"),
    ],
)
def test_binding_does_not_unicode_fold_suffix_title_or_substring(resource):
    source = _source("WakeIp", title="En_WakeIp.mp3", audio_id="WakeUp")

    record = bind_voice_row(source, index_voice_resources([resource]))

    assert record.status is BindingStatus.SHORTFALL
    assert record.matches == ()


@pytest.mark.parametrize(
    ("resources", "expected_status"),
    [
        ([], BindingStatus.SHORTFALL),
        (
            [
                _resource("En_WakeUp.mp3", sha256="b" * 64),
                _resource("en_wakeup.mp3", sha1="c" * 40, sha256="d" * 64),
            ],
            BindingStatus.FATAL,
        ),
    ],
)
def test_zero_match_is_shortfall_and_distinct_sha_is_fatal(resources, expected_status):
    record = bind_voice_row(_source("WakeUp"), index_voice_resources(resources))

    assert record.status is expected_status


def test_binding_requires_computable_sha256_before_exact_or_fatal_classification():
    resource = _resource(
        "En_WakeUp.mp3",
        sha256="",
        local_relpath="assets/files/a/WakeUp.mp3",
    )

    record = bind_voice_row(_source("WakeUp"), index_voice_resources([resource]))

    assert record.status is BindingStatus.SHORTFALL
    assert record.matches == (resource,)


@pytest.mark.parametrize(
    ("source", "resource"),
    [
        (_source("WakeUp", "tw"), _resource("Zh_WakeUp.mp3", "zh")),
        (_source("WakeUp", "zh"), _resource("Tw_WakeUp.mp3", "tw")),
        (_source("WakeUp", "en"), _resource("En_WakeUp.mp3", "jp")),
    ],
)
def test_binding_never_crosses_language_or_borrows_zh_for_tw(source, resource):
    record = bind_voice_row(source, index_voice_resources([resource]))

    assert record.status is BindingStatus.SHORTFALL
    assert record.matches == ()


@pytest.mark.parametrize(
    ("resources", "expected_status"),
    [
        ([_resource("En_Arrival.mp3")], BindingStatus.SHORTFALL),
        ([_resource("En_Skin_Arrival.mp3")], BindingStatus.SHORTFALL),
        ([_resource("En_SkinArrival.mp3")], BindingStatus.EXACT),
    ],
)
def test_skin_event_name_not_audio_suffix_is_authority(resources, expected_status):
    source = _source("SkinArrival", audio_id="Arrival", title="Arrival")

    record = bind_voice_row(source, index_voice_resources(resources))

    assert record.status is expected_status
    assert record.expected_filename == "En_SkinArrival.mp3"


@pytest.mark.parametrize(
    ("sha1", "expected"),
    [
        ("a" * 40, "media:sha1:" + "a" * 40),
        ("ABCDEF0123456789ABCDEF0123456789ABCDEF01", "media:sha1:abcdef0123456789abcdef0123456789abcdef01"),
    ],
)
def test_media_id_uses_full_sha1_protocol(sha1, expected):
    assert media_id_for_sha1(sha1) == expected

    for invalid in ("", "a" * 39, "a" * 41, "g" * 40, "a" * 20 + "-" + "a" * 19):
        with pytest.raises(ValueError):
            media_id_for_sha1(invalid)
