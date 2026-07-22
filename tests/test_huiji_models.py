import hashlib
from pathlib import PurePosixPath

import pytest

from src.huijiwiki.errors import ReadOnlyViolation
from src.huijiwiki.models import (
    FetchDecision,
    PageIndexRecord,
    ResourceRecord,
    RevisionRecord,
    build_source_url,
    ensure_read_only_action,
    stable_resource_relpath,
)
from src.huiji_rag.models import BindingRecord, BindingStatus, ResourceRow, VoiceSourceRow


def test_build_source_url_encodes_spaces_and_keeps_namespace_colon():
    assert build_source_url("槲寄生 档案") == (
        "https://res1999.huijiwiki.com/wiki/%E6%A7%B2%E5%AF%84%E7%94%9F_%E6%A1%A3%E6%A1%88"
    )
    assert build_source_url("Data:Episode/1402110.json").endswith(
        "/wiki/Data:Episode/1402110.json"
    )


def test_read_only_action_guard_accepts_query_and_rejects_write_actions():
    ensure_read_only_action({"action": "query"})
    ensure_read_only_action({})

    for action in ["edit", "upload", "delete", "move", "purge", "rollback"]:
        with pytest.raises(ReadOnlyViolation):
            ensure_read_only_action({"action": action})


def test_page_revision_and_resource_records_serialize_expected_fields():
    page = PageIndexRecord(
        site="res1999",
        pageid=10,
        ns=3500,
        title="Data:Example.json",
        lastrevid=99,
        length=123,
        touched="2026-07-02T00:00:00Z",
        seen_at="2026-07-02T08:00:00+08:00",
    )
    assert page.to_json()["source_url"].endswith("/wiki/Data:Example.json")

    rev = RevisionRecord(
        site="res1999",
        pageid=10,
        ns=3500,
        title="Data:Example.json",
        revid=99,
        timestamp="2026-07-02T00:00:00Z",
        content_model="json",
        content_format="application/json",
        content='{"name":"test"}',
        fetched_at="2026-07-02T08:00:01+08:00",
    )
    payload = rev.to_json()
    assert payload["content_sha256"]
    assert payload["content"] == '{"name":"test"}'

    relpath = stable_resource_relpath(name="角色立绘.png", sha1="abc123", pageid=None)
    assert PurePosixPath(relpath).parts == ("assets", "files", "abc123", "角色立绘.png")

    resource = ResourceRecord(
        site="res1999",
        source="huiji_file_namespace",
        title="File:角色立绘.png",
        name="角色立绘.png",
        url="https://img.example/角色立绘.png",
        descriptionurl="https://res1999.huijiwiki.com/wiki/File:%E8%A7%92%E8%89%B2",
        mime="image/png",
        size=1024,
        width=512,
        height=512,
        sha1="abc123",
        timestamp="2026-07-02T00:00:00Z",
        local_relpath=relpath,
        download_status="not_downloaded",
        seen_at="2026-07-02T08:00:00+08:00",
    )
    assert resource.to_json()["download_status"] == "not_downloaded"


def test_fetch_decision_is_explicit():
    decision = FetchDecision(pageid=10, should_fetch=True, reason="changed")
    assert decision.to_json() == {
        "pageid": 10,
        "should_fetch": True,
        "reason": "changed",
    }


@pytest.mark.parametrize(
    ("resources", "status", "expected_resource_ids"),
    [
        ([], BindingStatus.SHORTFALL, ()),
        (
            [
                ResourceRow(
                    filename="En_WakeUp.mp3",
                    language="en",
                    sha1="a" * 40,
                    sha256="b" * 64,
                    resource_id="resource:1",
                    source_id="manifest:1",
                    local_relpath="assets/files/a/En_WakeUp.mp3",
                    object_key="voice/en/a.mp3",
                )
            ],
            BindingStatus.EXACT,
            ("resource:1",),
        ),
        (
            [
                ResourceRow(
                    filename="En_WakeUp.mp3",
                    language="en",
                    sha1="a" * 40,
                    sha256="b" * 64,
                    resource_id="resource:1",
                    source_id="manifest:1",
                    local_relpath="assets/files/a/En_WakeUp.mp3",
                    object_key="voice/en/a.mp3",
                ),
                ResourceRow(
                    filename="en_wakeup.mp3",
                    language="en",
                    sha1="c" * 40,
                    sha256="d" * 64,
                    resource_id="resource:2",
                    source_id="manifest:2",
                    local_relpath="assets/files/c/en_wakeup.mp3",
                    object_key="voice/en/c.mp3",
                ),
            ],
            BindingStatus.FATAL,
            ("resource:1", "resource:2"),
        ),
    ],
)
def test_binding_record_retains_explicit_source_text_and_resource_evidence(
    resources, status, expected_resource_ids
):
    source = VoiceSourceRow(
        event_name="WakeUp",
        language="en",
        source_id="voice:1",
        entity_id="character:1",
        parent_id="parent:1",
        child_id="child:1",
        skin_id="skin:1",
        transcript="Wake up.",
        quality_flags=("verified",),
    )

    record = BindingRecord.from_match(source, "En_WakeUp.mp3", resources, status)
    payload = record.to_json()

    assert record.source == source
    assert record.expected_filename == "En_WakeUp.mp3"
    assert record.matches == tuple(resources)
    assert record.status is status
    assert record.binding_status is status
    assert record.source_id == "voice:1"
    assert record.entity_id == "character:1"
    assert record.parent_id == "parent:1"
    assert record.child_id == "child:1"
    assert record.skin_id == "skin:1"
    assert record.resource_ids == expected_resource_ids
    assert record.resource_filenames == tuple(item.filename for item in resources)
    assert record.source_sha1 == tuple(item.sha1 for item in resources)
    assert record.content_sha256 == tuple(item.sha256 for item in resources)
    assert record.object_key == tuple(item.object_key for item in resources)
    assert record.local_relpath == tuple(item.local_relpath for item in resources)
    assert record.text_sha256 == hashlib.sha256(b"Wake up.").hexdigest()
    assert record.quality_flags == ("verified",)
    assert record.evidence_ids == ("voice:1",) + expected_resource_ids
    assert payload["transcript"] == "Wake up."
    assert payload["resource_filenames"] == [item.filename for item in resources]
