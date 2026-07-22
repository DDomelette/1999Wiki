import importlib
import base64
import itertools
import json
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from urllib.parse import quote

import pytest


voice_pagination = importlib.import_module("src.assets.voice_pagination")


def _encode_rounds(value, rounds):
    encoded = value
    for _index in range(rounds):
        encoded = quote(encoded, safe="")
    return encoded


def _voice_row(
    media_id,
    child_id,
    language,
    *,
    entity_id="entity-a",
    parent_id="entity-a/voice",
    filename=None,
    title="",
    mime="audio/mpeg",
    url=None,
    available=True,
    sort_order=0,
):
    extension = "ogg" if mime == "audio/ogg" else "mp3"
    return {
        "media_id": media_id,
        "entity_id": entity_id,
        "entity_name": entity_id,
        "child_id": child_id,
        "parent_id": parent_id,
        "asset_type": "voice",
        "filename": filename or f"{language}_line.{extension}",
        "title": title,
        "mime": mime,
        "url": url or f"https://media.example/{media_id}.{extension}",
        "is_available": available,
        "is_common": False,
        "attach_policy": "on_intent",
        "sort_order": sort_order,
        "language": language,
    }


def _decode_cursor_wrapper(cursor):
    padded = cursor + "=" * (-len(cursor) % 4)
    return json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))


def test_voice_pagination_contracts_are_available():
    module = importlib.import_module("src.assets.voice_pagination")

    assert module.VoiceLineGroup
    assert module.VoicePanelPage
    assert issubclass(module.InvalidVoiceCursor, ValueError)
    assert issubclass(module.VoiceCursorBuildMismatch, ValueError)


def test_groups_playable_http_audio_by_child_with_ordered_real_variants():
    child_id = "entity-a/voice:0002"
    rows = [
        _voice_row("fr", child_id, "fr", sort_order=4),
        _voice_row("en", child_id, "en", sort_order=3),
        _voice_row("zh-ogg", child_id, "zh", mime="audio/ogg", sort_order=2),
        _voice_row("zh-mp3", child_id, "zh", sort_order=1),
        _voice_row("local", child_id, "jp", url="D:\\voice.mp3"),
        _voice_row("missing", child_id, "kr", available=False),
        _voice_row("not-audio", "entity-a/voice:0003", "zh", mime="image/png"),
        _voice_row(
            "foreign",
            "entity-b/voice:0002",
            "kr",
            entity_id="entity-b",
            parent_id="entity-b/voice",
        ),
    ]

    groups = voice_pagination.build_voice_line_groups(
        rows,
        {child_id: {"zh": "中文台词", "en": "English line"}},
    )

    assert [group.voice_line_id for group in groups] == [child_id, "entity-b/voice:0002"]
    entity_a = groups[0]
    assert entity_a.title == "中文台词"
    assert [variant["language"] for variant in entity_a.variants] == ["zh", "en", "fr"]
    assert [variant["media_id"] for variant in entity_a.variants] == ["zh-mp3", "en", "fr"]
    assert all(variant["url"].startswith(("http://", "https://")) for variant in entity_a.variants)


def test_reused_artifact_media_ids_keep_every_playable_line_and_remain_visible():
    rows = [
        _voice_row("shared", "entity-a/voice:0001", "zh"),
        _voice_row("first-only", "entity-a/voice:0001", "en"),
        _voice_row("shared", "entity-a/voice:0002", "zh"),
        _voice_row("second-only", "entity-a/voice:0002", "en"),
        _voice_row("shared", "entity-a/voice:0003", "zh"),
    ]

    groups = voice_pagination.build_voice_line_groups(rows, {})

    assert [group.voice_line_id for group in groups] == [
        "entity-a/voice:0001",
        "entity-a/voice:0002",
        "entity-a/voice:0003",
    ]
    media_ids = [
        variant["media_id"]
        for group in groups
        for variant in group.variants
    ]
    assert media_ids == ["shared", "first-only", "shared", "second-only", "shared"]
    assert [
        variant["asset_id"]
        for group in groups
        for variant in group.variants
    ] == media_ids

    index = voice_pagination.VoicePaginationIndex(rows, {}, build_version="build-a")
    page = index.first_page("entity-a", "entity-a/voice", page_size=1)
    observed_line_ids = []
    while True:
        observed_line_ids.extend(line.voice_line_id for line in page.lines)
        if not page.next_cursor:
            break
        page = index.get_page(page.next_cursor)
    assert observed_line_ids == [
        "entity-a/voice:0001",
        "entity-a/voice:0002",
        "entity-a/voice:0003",
    ]


def test_v3_binding_ids_remain_distinct_when_compatibility_media_id_is_reused():
    first = _voice_row("shared", "entity-a/voice:0001", "zh-cn")
    first.update({
        "binding_id": "binding:sha256:" + "1" * 64,
        "resource_id": "resource:sha256:" + "a" * 64,
        "media_role": "voice",
    })
    second = _voice_row("shared", "entity-a/voice:0002", "en-us")
    second.update({
        "binding_id": "binding:sha256:" + "2" * 64,
        "resource_id": "resource:sha256:" + "a" * 64,
        "media_role": "voice",
    })

    groups = voice_pagination.build_voice_line_groups([first, second], {})
    variants = [variant for group in groups for variant in group.variants]

    assert [variant["media_id"] for variant in variants] == ["shared", "shared"]
    assert [variant["asset_id"] for variant in variants] == [
        first["binding_id"],
        second["binding_id"],
    ]
    assert [variant["binding_id"] for variant in variants] == [
        first["binding_id"],
        second["binding_id"],
    ]
    assert [variant["language"] for variant in variants] == ["zh-cn", "en-us"]


@pytest.mark.parametrize(
    "unsafe_url",
    [
        "https://media.example/voice.mp3?source=Z:\\private\\voice.mp3",
        "https://media.example/voice.mp3?source=q:/private/voice.mp3",
        "https://media.example/voice.mp3?source=FiLe://server/private.mp3",
        "https://media.example/voice/../private/voice.mp3",
        "https://media.example/voice\\..\\private\\voice.mp3",
        "https://media.example/voice.mp3?source=X%3A%5Cprivate%5Cvoice.mp3",
        "https://media.example/voice.mp3?source=y%3A%2Fprivate%2Fvoice.mp3",
        "https://media.example/voice.mp3?source=fIlE%3A%2F%2Fprivate%2Fvoice.mp3",
        "https://media.example/voice/%2e%2e%2fprivate%2fvoice.mp3",
        "file:/etc/passwd",
        "file:\\server\\share\\voice.mp3",
        "https://media.example/voice.mp3?source=file:/etc/passwd",
        "https://media.example/voice.mp3?source=file:\\server\\share\\voice.mp3",
        "https://media.example/voice.mp3?source=FILE%3A%5C%5Cserver%5Cshare%5Cvoice.mp3",
        "https://media.example/voice.mp3?source=\\\\server\\share\\voice.mp3",
        "https://media.example/voice/\\\\server\\share\\voice.mp3",
        "https://media.example/voice/"
        + _encode_rounds("%2E%2E%2Fprivate%2Fvoice.mp3", 3),
        "https://media.example/voice.mp3?value="
        + _encode_rounds("%2Fstill-changing", 32),
    ],
)
def test_grouping_rejects_generic_and_encoded_local_path_markers(unsafe_url):
    row = _voice_row("unsafe", "entity-a/voice:0001", "zh", url=unsafe_url)

    assert voice_pagination.build_voice_line_groups([row], {}) == ()


def test_grouping_keeps_valid_http_object_keys_without_local_markers():
    url = (
        "https://media.example/reverse1999/voice/folder..name/zh_line.mp3"
        "?redirect=https%3A%2F%2Fcdn.example%2Fvoice%2Fzh_line.mp3"
    )
    row = _voice_row("safe", "entity-a/voice:0001", "zh", url=url)

    groups = voice_pagination.build_voice_line_groups([row], {})

    assert groups[0].variants[0]["url"] == url


def test_group_title_falls_back_to_any_transcript_then_stable_media_title():
    english_child = "entity-a/voice:0001"
    file_child = "entity-a/voice:0002"
    rows = [
        _voice_row("english", english_child, "en", title="English file title"),
        _voice_row("file", file_child, "jp", title="Stable file title"),
    ]

    groups = voice_pagination.build_voice_line_groups(
        rows,
        {english_child: {"en": "Only transcript"}},
    )

    assert [group.title for group in groups] == ["Only transcript", "Stable file title"]


def test_line_order_uses_parent_numeric_suffix_then_existing_sort_order():
    rows = [
        _voice_row("p2-1", "entity-a/voice-alt:0001", "zh", parent_id="z-parent", sort_order=0),
        _voice_row("p1-10", "entity-a/voice:0010", "zh", parent_id="a-parent", sort_order=0),
        _voice_row("p1-2-late", "entity-a/voice:0002", "en", parent_id="a-parent", sort_order=8),
        _voice_row("p1-2-early", "entity-a/voice:0002", "zh", parent_id="a-parent", sort_order=3),
    ]

    groups = voice_pagination.build_voice_line_groups(rows, {})

    assert [group.voice_line_id for group in groups] == [
        "entity-a/voice:0002",
        "entity-a/voice:0010",
        "entity-a/voice-alt:0001",
    ]


def test_index_derives_missing_entity_id_from_consistent_identifier_prefixes():
    row = _voice_row(
        "derived-scope",
        "char:100/voice:0001",
        "zh",
        parent_id="char:100/voice",
    )
    row.pop("entity_id")
    row["entity_name"] = "目标角色"
    index = voice_pagination.VoicePaginationIndex([row], {}, build_version="build-a")

    page = index.first_page("char:100", "char:100/voice")

    assert page.entity_id == "char:100"
    assert [line.voice_line_id for line in page.lines] == ["char:100/voice:0001"]
    assert page.lines[0].variants[0]["entity_id"] == "char:100"


def test_index_canonicalizes_actual_bare_entity_id_to_agreed_artifact_scope():
    rows = [
        _voice_row(
            "voice-1-en",
            "char:3003/voice:1300301",
            "en",
            entity_id="3003",
            parent_id="char:3003/voice",
        ),
        _voice_row(
            "voice-1-jp",
            "char:3003/voice:1300301",
            "jp",
            entity_id="3003",
            parent_id="char:3003/voice",
        ),
        _voice_row(
            "voice-2-zh",
            "char:3003/voice:1300302",
            "zh",
            entity_id="3003",
            parent_id="char:3003/voice",
        ),
    ]
    index = voice_pagination.VoicePaginationIndex(rows, {}, build_version="build-a")

    first = index.first_page("char:3003", "char:3003/voice", page_size=1)

    assert first.entity_id == "char:3003"
    assert first.total_lines == 2
    assert [line.voice_line_id for line in first.lines] == ["char:3003/voice:1300301"]
    assert [variant["media_id"] for variant in first.lines[0].variants] == [
        "voice-1-en",
        "voice-1-jp",
    ]
    assert first.next_cursor


def test_entity_scope_suffix_equivalence_is_generic_but_conflicts_stay_invalid():
    assert voice_pagination.derive_entity_scope(
        "role-alpha",
        "npc:role-alpha/voice:0001",
        "npc:role-alpha/voice",
    ) == "npc:role-alpha"
    assert voice_pagination.derive_entity_scope(
        "other-role",
        "npc:role-alpha/voice:0001",
        "npc:role-alpha/voice",
    ) is None
    assert voice_pagination.derive_entity_scope(
        "other:role-alpha",
        "npc:role-alpha/voice:0001",
        "npc:role-alpha/voice",
    ) is None
    assert voice_pagination.derive_entity_scope(
        "role-alpha",
        "npc:role-alpha/voice:0001",
        "char:role-alpha/voice",
    ) is None


def test_pages_default_and_clamp_size_and_repeat_cursor_byte_equivalently():
    rows = [
        _voice_row(f"media-{index}", f"entity-a/voice:{index:04d}", "zh", sort_order=index)
        for index in range(1, 23)
    ]
    index = voice_pagination.VoicePaginationIndex(rows, {}, build_version="build-a")

    default_page = index.first_page("entity-a", "entity-a/voice")
    small_page = index.first_page("entity-a", "entity-a/voice", page_size=0)
    first = index.first_page("entity-a", "entity-a/voice", page_size=99)

    assert default_page.page_size == 8
    assert len(default_page.lines) == 8
    assert small_page.page_size == 1
    assert len(small_page.lines) == 1
    assert first.page_size == 20
    assert len(first.lines) == 20
    assert first.total_lines == 22
    assert first.has_more is True
    wrapper = _decode_cursor_wrapper(first.next_cursor)
    assert set(wrapper) == {"b", "t"}
    assert wrapper["b"] == "build-a"
    assert all(
        secret not in first.next_cursor
        for secret in ("entity-a", "entity-a/voice", "0020", "offset", "D:\\", "file://")
    )

    second = index.get_page(first.next_cursor)
    repeated = index.get_page(first.next_cursor)

    assert second.to_dict() == repeated.to_dict()
    assert json.dumps(second.to_dict(), sort_keys=True).encode() == json.dumps(
        repeated.to_dict(), sort_keys=True
    ).encode()
    assert [line.voice_line_id for line in second.lines] == [
        "entity-a/voice:0021",
        "entity-a/voice:0022",
    ]
    assert second.has_more is False
    assert second.next_cursor is None


def test_cursor_errors_distinguish_build_and_validate_current_scope_index():
    rows = [
        _voice_row("one", "entity-a/voice:0001", "zh"),
        _voice_row("two", "entity-a/voice:0002", "zh"),
        _voice_row(
            "foreign",
            "entity-b/voice:0001",
            "zh",
            entity_id="entity-b",
            parent_id="entity-b/voice",
        ),
    ]
    store = voice_pagination.VoiceCursorStore("build-a")
    index = voice_pagination.VoicePaginationIndex(
        rows,
        {},
        build_version="build-a",
        cursor_store=store,
    )
    first = index.first_page("entity-a", "entity-a/voice", page_size=1)

    assert [line.voice_line_id for line in first.lines] == ["entity-a/voice:0001"]
    with pytest.raises(voice_pagination.InvalidVoiceCursor):
        index.get_page("not-base64")
    with pytest.raises(voice_pagination.VoiceCursorBuildMismatch):
        voice_pagination.VoicePaginationIndex(rows, {}, build_version="build-b").get_page(
            first.next_cursor
        )
    with pytest.raises(voice_pagination.InvalidVoiceCursor):
        voice_pagination.VoicePaginationIndex(rows, {}, build_version="build-a").get_page(
            first.next_cursor
        )

    changed_index = voice_pagination.VoicePaginationIndex(
        rows[1:],
        {},
        build_version="build-a",
        cursor_store=store,
    )
    with pytest.raises(voice_pagination.InvalidVoiceCursor):
        changed_index.get_page(first.next_cursor)


def test_cursor_store_is_bounded_and_reuses_token_for_identical_state():
    store = voice_pagination.VoiceCursorStore("build-a", max_states=2)
    first = store.issue("entity-a", "parent", "line-1", 8)
    assert store.issue("entity-a", "parent", "line-1", 8) == first
    store.issue("entity-a", "parent", "line-2", 8)
    store.issue("entity-a", "parent", "line-3", 8)

    assert len(store) == 2
    assert {state: token for token, state in store._states.items()} == store._tokens
    with pytest.raises(voice_pagination.InvalidVoiceCursor):
        store.decode(first)


def test_concurrent_cursor_issue_returns_one_token_and_consistent_maps(monkeypatch):
    workers = 12
    barrier = Barrier(workers)
    counter = itertools.count()
    store = voice_pagination.VoiceCursorStore("build-a", max_states=32)

    def slow_token(_size):
        time.sleep(0.02)
        return f"token-{next(counter)}"

    monkeypatch.setattr(voice_pagination.secrets, "token_urlsafe", slow_token)

    def issue_same_state(_index):
        barrier.wait()
        return store.issue("entity-a", "parent", "line-1", 8)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        cursors = list(executor.map(issue_same_state, range(workers)))

    assert len(set(cursors)) == 1
    assert len(store) == 1
    assert {state: token for token, state in store._states.items()} == store._tokens


def test_concurrent_repeated_pages_are_byte_equivalent_including_next_cursor(monkeypatch):
    workers = 12
    rows = [
        _voice_row(f"media-{index}", f"entity-a/voice:{index:04d}", "zh")
        for index in range(1, 5)
    ]
    index = voice_pagination.VoicePaginationIndex(rows, {}, build_version="build-a")
    first = index.first_page("entity-a", "entity-a/voice", page_size=1)
    barrier = Barrier(workers)
    counter = itertools.count()

    def slow_token(_size):
        time.sleep(0.02)
        return f"page-token-{next(counter)}"

    monkeypatch.setattr(voice_pagination.secrets, "token_urlsafe", slow_token)

    def load_same_page(_index):
        barrier.wait()
        page = index.get_page(first.next_cursor)
        return json.dumps(page.to_dict(), ensure_ascii=False, sort_keys=True).encode("utf-8")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        pages = list(executor.map(load_same_page, range(workers)))

    assert len(set(pages)) == 1
    decoded = json.loads(pages[0])
    assert decoded["next_cursor"]
    store = index._cursor_store
    assert {state: token for token, state in store._states.items()} == store._tokens
    assert len(store) <= store.max_states
