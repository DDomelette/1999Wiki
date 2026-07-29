from __future__ import annotations

import hashlib

import pytest

from src.huiji_rag.build.contracts import canonical_mapping_jsonl_bytes
from src.huiji_rag.build.contracts import canonical_json_bytes
from src.huiji_rag.build.media_download_plan import (
    GIB,
    MIN_FREE_AFTER_COMMIT_BYTES,
    P0_MEDIA_NEW_BYTES_MAX,
    P1_MEDIA_CUMULATIVE_NEW_BYTES_MAX,
    MediaCapacityEvidence,
    MediaDownloadPlanRequest,
    apply_capacity_decision,
    build_media_download_plan,
)


SHA1_A = "1" * 40
SHA1_B = "2" * 40
SHA1_C = "3" * 40
SHA256_A = "a" * 64
SHA256_B = "b" * 64
SHA256_C = "c" * 64


def media_row(
    resource: str,
    *,
    binding: str,
    owner_id: str,
    size: int = 100,
    owner_type: str = "page",
    role: str = "representative",
    priority: int = 10,
    sha1: str = SHA1_A,
    sha256: str = SHA256_A,
    eligible: bool = True,
    local_present: bool = False,
) -> dict[str, object]:
    return {
        "resource_id": resource,
        "binding_id": binding,
        "owner_id": owner_id,
        "owner_type": owner_type,
        "media_role": role,
        "selection_priority": priority,
        "eligible": eligible,
        "filename": f"{resource}.png",
        "url": f"https://huiji-public.huijistatic.com/res1999/{resource}.png",
        "sha1": sha1,
        "content_sha256": sha256,
        "size": size,
        "local_relpath": f"assets/{sha1}/{resource}.png",
        "download_status": "downloaded" if local_present else "not_downloaded",
        "local_present": local_present,
        "object_key": f"reverse1999/image/{sha1}/{resource}.png",
    }


def request(
    rows: list[dict[str, object]],
    *,
    phase: str = "p0",
    free_local: int | None = 40 * GIB,
    cloud_free: int | None = 40 * GIB,
    other_growth: int | None = 0,
    baseline_rows: tuple[dict[str, object], ...] = (),
    candidate_bytes: int = 0,
    workers: int = 2,
    actual_free: int | None = None,
) -> MediaDownloadPlanRequest:
    return MediaDownloadPlanRequest(
        media_rows=tuple(rows),
        minio_inventory_rows=baseline_rows,
        source_inventory_fingerprint="s" * 64,
        projection_fingerprint="p" * 64,
        phase=phase,
        selection_policy_sha256="f" * 64,
        media_budget_baseline_inventory_sha256="d" * 64,
        workers=workers,
        capacity=MediaCapacityEvidence(
            free_local_bytes=free_local,
            known_cloud_free_or_quota_bytes=cloud_free,
            other_storage_growth_bytes=other_growth,
            candidate_artifact_estimate_bytes=candidate_bytes,
            actual_free_after_commit_bytes=actual_free,
        ),
    )


def test_allowlist_contains_only_referenced_eligible_exact_resources() -> None:
    rows = [
        media_row("selected", binding="binding:1", owner_id="page:1"),
        media_row(
            "unreferenced",
            binding="",
            owner_id="page:2",
        ),
        media_row(
            "decorative",
            binding="binding:3",
            owner_id="page:3",
            role="decorative_icon",
        ),
        media_row(
            "unsupported",
            binding="binding:4",
            owner_id="story:1",
            owner_type="story",
            role="background",
        ),
    ]

    result = build_media_download_plan(request(rows))

    assert [row["resource_id"] for row in result.allowlist_rows] == ["selected"]
    assert {row["resource_id"] for row in result.report["not_eligible"]} == {
        "decorative",
        "unreferenced",
        "unsupported",
    }


def test_allowlist_preserves_all_bindings_while_physical_bytes_are_deduplicated() -> None:
    first = media_row("shared", binding="binding:1", owner_id="page:1", size=50)
    first["heading_path"] = ["剧情", "第一节"]
    first["context_digest"] = "c" * 64
    second = {
        **first,
        "binding_id": "binding:2",
        "owner_id": "page:2",
        "heading_path": ["剧情", "第二节"],
    }

    result = build_media_download_plan(request([second, first]))
    allowlist = result.allowlist_rows[0]

    assert allowlist["binding_ids"] == ["binding:1", "binding:2"]
    assert [row["heading_path"] for row in allowlist["bindings"]] == [
        ["剧情", "第一节"],
        ["剧情", "第二节"],
    ]
    assert result.report["capacity_totals"]["declared_bytes_total"] == 50
    assert result.report["capacity_totals"]["selected_media_new_bytes"] == 50


def test_p0_shared_object_covers_uncovered_owner_without_losing_bindings() -> None:
    first = media_row(
        "first",
        binding="binding:first",
        owner_id="page:1",
        priority=1,
    )
    shared_page_one = media_row(
        "shared",
        binding="binding:shared:1",
        owner_id="page:1",
        priority=2,
        sha1=SHA1_B,
        sha256=SHA256_B,
    )
    shared_page_two = {
        **shared_page_one,
        "binding_id": "binding:shared:2",
        "owner_id": "page:2",
    }

    result = build_media_download_plan(
        request([shared_page_two, first, shared_page_one])
    )
    rows = {row["resource_id"]: row for row in result.allowlist_rows}

    assert set(rows) == {"first", "shared"}
    assert rows["shared"]["binding_ids"] == [
        "binding:shared:1",
        "binding:shared:2",
    ]
    assert rows["shared"]["representative_owner_pairs"] == [
        ["page", "page:2"]
    ]
    assigned = [
        tuple(pair)
        for row in result.allowlist_rows
        for pair in row["representative_owner_pairs"]
    ]
    assert sorted(assigned) == [
        ("page", "page:1"),
        ("page", "page:2"),
    ]


def test_capacity_totals_separate_declared_local_missing_minio_new_and_peak_bytes() -> None:
    rows = [
        media_row(
            "local",
            binding="binding:1",
            owner_id="page:1",
            size=20,
            local_present=True,
        ),
        media_row(
            "missing",
            binding="binding:2",
            owner_id="page:2",
            size=30,
            sha1=SHA1_B,
            sha256=SHA256_B,
        ),
    ]

    result = build_media_download_plan(request(rows, candidate_bytes=7, workers=3))
    totals = result.report["capacity_totals"]

    assert totals["declared_bytes_total"] == 50
    assert totals["existing_valid_local_bytes"] == 20
    assert totals["missing_local_bytes"] == 30
    assert totals["largest_missing_resource_bytes"] == 30
    assert totals["concurrent_part_peak_bytes"] == 30
    assert totals["candidate_artifact_estimate_bytes"] == 7
    assert totals["MinIO_new_object_bytes"] == 50


def test_local_margin_uses_max_2gib_or_twenty_percent() -> None:
    small = build_media_download_plan(
        request([media_row("small", binding="b", owner_id="page:1")])
    )
    large = build_media_download_plan(
        request(
            [media_row("large", binding="b", owner_id="page:1")],
            phase="p1",
            candidate_bytes=11 * GIB,
        )
    )

    assert small.report["local_margin_bytes"] == 2 * GIB
    large_subtotal = 11 * GIB + 200
    assert large.report["local_margin_bytes"] == (
        large_subtotal * 20 + 99
    ) // 100


def test_cloud_margin_uses_max_1gib_or_twenty_percent() -> None:
    small = build_media_download_plan(
        request([media_row("small", binding="b", owner_id="page:1")])
    )
    overflow = build_media_download_plan(
        request(
            [media_row("large", binding="b", owner_id="page:1", size=6 * GIB)],
            phase="p1",
        )
    )

    assert small.report["cloud_margin_bytes"] == GIB
    assert overflow.report["cloud_margin_bytes"] == GIB


def test_current_capacity_uses_selected_set_while_overflow_keeps_full_forecast() -> None:
    selected = media_row(
        "selected",
        binding="binding:selected",
        owner_id="page:selected",
        size=10,
        priority=1,
    )
    overflow = media_row(
        "overflow",
        binding="binding:overflow",
        owner_id="page:overflow",
        size=20 * GIB,
        priority=2,
        sha1=SHA1_B,
        sha256=SHA256_B,
    )

    result = build_media_download_plan(
        request(
            [overflow, selected],
            free_local=20 * GIB,
            cloud_free=2 * GIB,
            workers=2,
        )
    )
    totals = result.report["capacity_totals"]

    assert result.state == "capacity_blocked"
    assert totals["unique_resource_count"] == 1
    assert totals["declared_bytes_total"] == 10
    assert totals["missing_local_bytes"] == 10
    assert totals["concurrent_part_peak_bytes"] == 10
    assert totals["MinIO_new_object_bytes"] == 10
    assert totals["selected_media_new_bytes"] == 10
    assert result.report["local_margin_bytes"] == 2 * GIB
    assert result.report["cloud_margin_bytes"] == GIB
    assert result.report["referenced_totals"]["unique_resource_count"] == 2
    assert result.report["referenced_totals"]["declared_bytes_total"] == (
        20 * GIB + 10
    )
    assert result.report["overflow_forecast"]["new_object_bytes"] == 20 * GIB


@pytest.mark.parametrize(
    ("cloud_free", "other_growth"),
    [(None, 0), (40 * GIB, None)],
)
def test_unknown_cloud_or_other_storage_growth_is_not_zero_or_sufficient(
    cloud_free: int | None,
    other_growth: int | None,
) -> None:
    result = build_media_download_plan(
        request(
            [media_row("one", binding="b", owner_id="page:1")],
            cloud_free=cloud_free,
            other_growth=other_growth,
        )
    )

    assert result.state == "unknown_capacity"
    assert result.report["capacity_sufficient"] is None
    assert result.report["projected_free_after_commit_bytes"] is None


def test_exact_existing_minio_key_sha_size_reuses_without_new_byte_charge() -> None:
    row = media_row("one", binding="b", owner_id="page:1", size=99)
    reused = {
        "object_key": row["object_key"],
        "sha1": row["sha1"],
        "content_sha256": row["content_sha256"],
        "size": 99,
    }
    mismatch = {**reused, "size": 100}

    exact = build_media_download_plan(request([row], baseline_rows=(reused,)))
    changed = build_media_download_plan(request([row], baseline_rows=(mismatch,)))

    assert exact.report["capacity_totals"]["MinIO_existing_object_bytes"] == 99
    assert exact.report["capacity_totals"]["MinIO_new_object_bytes"] == 0
    assert changed.report["capacity_totals"]["MinIO_new_object_bytes"] == 99


def test_conflicting_resource_id_identity_fails_closed() -> None:
    first = media_row("same", binding="binding:1", owner_id="page:1")
    conflicting = media_row(
        "same",
        binding="binding:2",
        owner_id="page:2",
        sha1=SHA1_B,
        sha256=SHA256_B,
    )

    with pytest.raises(ValueError, match="resource_id identity conflict"):
        build_media_download_plan(request([first, conflicting]))


def test_conflicting_object_key_identity_fails_closed() -> None:
    first = media_row("first", binding="binding:1", owner_id="page:1")
    conflicting = media_row(
        "second",
        binding="binding:2",
        owner_id="page:2",
        sha1=SHA1_B,
        sha256=SHA256_B,
    )
    conflicting["object_key"] = first["object_key"]

    with pytest.raises(ValueError, match="object_key identity conflict"):
        build_media_download_plan(request([first, conflicting]))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sha1", "not-a-sha1"),
        ("content_sha256", "A" * 64),
        ("size", -1),
        ("size", 1.5),
    ],
)
def test_malformed_candidate_identity_fails_closed(
    field: str,
    value: object,
) -> None:
    row = media_row("bad", binding="binding:bad", owner_id="page:bad")
    row[field] = value

    with pytest.raises(ValueError, match="candidate resource identity"):
        build_media_download_plan(request([row]))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("object_key", None),
        ("sha1", "not-a-sha1"),
        ("content_sha256", "A" * 64),
        ("size", -1),
        ("size", 1.5),
    ],
)
def test_malformed_minio_inventory_never_reduces_new_byte_accounting(
    field: str,
    value: object,
) -> None:
    row = media_row("one", binding="binding:one", owner_id="page:1", size=99)
    baseline = {
        "object_key": row["object_key"],
        "sha1": row["sha1"],
        "content_sha256": row["content_sha256"],
        "size": row["size"],
    }
    baseline[field] = value

    with pytest.raises(ValueError, match="MinIO inventory identity"):
        build_media_download_plan(request([row], baseline_rows=(baseline,)))


def test_selection_policy_and_allowlist_sha_are_deterministic() -> None:
    rows = [
        media_row("b", binding="binding:2", owner_id="page:2", sha1=SHA1_B, sha256=SHA256_B),
        media_row("a", binding="binding:1", owner_id="page:1"),
    ]

    forward = build_media_download_plan(request(rows))
    reverse = build_media_download_plan(request(list(reversed(rows))))

    assert forward.plan == reverse.plan
    assert forward.report == reverse.report
    assert forward.allowlist_sha256 == reverse.allowlist_sha256
    assert forward.allowlist_sha256 == hashlib.sha256(
        canonical_mapping_jsonl_bytes(forward.allowlist_rows)
    ).hexdigest()


def test_canonical_artifacts_have_frozen_names_and_exact_payload_bytes() -> None:
    result = build_media_download_plan(
        request([media_row("one", binding="binding:1", owner_id="page:1")])
    )

    assert result.artifact_bytes() == {
        "media_capacity_report.v1.json": canonical_json_bytes(dict(result.report)),
        "referenced_media_allowlist.v1.jsonl": canonical_mapping_jsonl_bytes(
            result.allowlist_rows
        ),
        "referenced_media_plan.v1.json": canonical_json_bytes(dict(result.plan)),
    }
    assert result.plan["resources"] == list(result.allowlist_rows)


def test_p0_selects_at_most_one_representative_per_main_page_activity_or_chapter() -> None:
    rows = [
        media_row("second", binding="b2", owner_id="page:1", priority=20, sha1=SHA1_B, sha256=SHA256_B),
        media_row("first", binding="b1", owner_id="page:1", priority=10),
        media_row("activity", binding="b3", owner_id="activity:1", owner_type="activity"),
        media_row("chapter", binding="b4", owner_id="chapter:1", owner_type="chapter"),
    ]

    result = build_media_download_plan(request(rows))

    assert [row["resource_id"] for row in result.allowlist_rows] == [
        "activity",
        "chapter",
        "first",
    ]
    excluded = {row["resource_id"]: row["reason_code"] for row in result.report["not_eligible"]}
    assert excluded["second"] == "p0_owner_representative_limit"


@pytest.mark.parametrize("role", ["background", "cg", "avatar", "decorative_icon", "audio"])
def test_story_background_cg_avatar_and_decorative_icons_are_not_p0_physical_objects(
    role: str,
) -> None:
    result = build_media_download_plan(
        request(
            [
                media_row(
                    role,
                    binding=f"binding:{role}",
                    owner_id="story:1",
                    owner_type="story",
                    role=role,
                )
            ]
        )
    )

    assert result.allowlist_rows == ()
    expected = (
        "decorative_resource"
        if role == "decorative_icon"
        else "p0_role_not_eligible"
    )
    assert result.report["not_eligible"][0]["reason_code"] == expected


def test_p0_over_256_mib_returns_capacity_blocked_without_random_truncation() -> None:
    rows = [
        media_row("a", binding="a", owner_id="page:a", size=200 * 1024 * 1024),
        media_row(
            "b",
            binding="b",
            owner_id="page:b",
            size=100 * 1024 * 1024,
            sha1=SHA1_B,
            sha256=SHA256_B,
        ),
    ]

    result = build_media_download_plan(request(rows))

    assert result.state == "capacity_blocked"
    assert result.report["media_budget_bytes"] == P0_MEDIA_NEW_BYTES_MAX
    assert [row["resource_id"] for row in result.report["selected_within_budget"]] == ["a"]
    assert [row["resource_id"] for row in result.report["phase_overflow"]] == ["b"]


def test_p1_cumulative_over_2_gib_returns_capacity_blocked_against_frozen_baseline() -> None:
    rows = [
        media_row("a", binding="a", owner_id="page:a", size=2 * GIB),
        media_row(
            "b",
            binding="b",
            owner_id="page:b",
            size=1,
            sha1=SHA1_B,
            sha256=SHA256_B,
        ),
    ]

    result = build_media_download_plan(request(rows, phase="p1"))

    assert result.state == "capacity_blocked"
    assert result.report["media_budget_bytes"] == P1_MEDIA_CUMULATIVE_NEW_BYTES_MAX
    assert result.plan["media_budget_baseline_inventory_sha256"] == "d" * 64


@pytest.mark.parametrize("actual_free", [None, MIN_FREE_AFTER_COMMIT_BYTES - 1])
def test_projected_or_actual_free_below_12_gib_never_accepts_or_readies(
    actual_free: int | None,
) -> None:
    free_local = MIN_FREE_AFTER_COMMIT_BYTES if actual_free is None else 40 * GIB
    result = build_media_download_plan(
        request(
            [media_row("one", binding="b", owner_id="page:1")],
            free_local=free_local,
            actual_free=actual_free,
        )
    )

    assert result.state == "capacity_blocked"
    assert result.report["capacity_sufficient"] is False


def test_capacity_blocked_partitions_selected_overflow_and_not_eligible() -> None:
    rows = [
        media_row(
            "selected",
            binding="a",
            owner_id="page:a",
            size=P0_MEDIA_NEW_BYTES_MAX,
            priority=1,
        ),
        media_row(
            "overflow",
            binding="b",
            owner_id="page:b",
            size=1,
            sha1=SHA1_B,
            sha256=SHA256_B,
        ),
        media_row(
            "icon",
            binding="c",
            owner_id="page:c",
            role="decorative_icon",
            sha1=SHA1_C,
            sha256=SHA256_C,
        ),
    ]

    result = build_media_download_plan(request(rows))

    sets = (
        {row["resource_id"] for row in result.report["selected_within_budget"]},
        {row["resource_id"] for row in result.report["phase_overflow"]},
        {row["resource_id"] for row in result.report["not_eligible"]},
    )
    assert sets == ({"selected"}, {"overflow"}, {"icon"})
    assert not (sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2])


def test_overflow_forecast_reports_resource_binding_groups_reuse_and_peak() -> None:
    overflow = media_row(
        "overflow",
        binding="b1",
        owner_id="page:b",
        size=100,
        sha1=SHA1_B,
        sha256=SHA256_B,
    )
    duplicate_binding = {**overflow, "binding_id": "b2"}
    rows = [
        media_row(
            "selected",
            binding="a",
            owner_id="page:a",
            size=P0_MEDIA_NEW_BYTES_MAX,
            priority=1,
        ),
        overflow,
        duplicate_binding,
    ]

    result = build_media_download_plan(request(rows))
    forecast = result.report["overflow_forecast"]

    assert forecast["resource_count"] == 1
    assert forecast["binding_count"] == 2
    assert forecast["new_object_bytes"] == 100
    assert forecast["largest_resource_bytes"] == 100
    assert forecast["concurrent_part_peak_bytes"] == 100
    assert forecast["by_owner_type"] == {"page": {"binding_count": 2, "resource_count": 1}}


def test_overflow_forecast_computes_projected_free_shortfall_minimum_and_5gib_roundup() -> None:
    rows = [
        media_row(
            "selected",
            binding="a",
            owner_id="page:a",
            size=P0_MEDIA_NEW_BYTES_MAX,
            priority=1,
        ),
        media_row(
            "overflow",
            binding="b",
            owner_id="page:b",
            size=100,
            sha1=SHA1_B,
            sha256=SHA256_B,
        ),
    ]
    free_local = MIN_FREE_AFTER_COMMIT_BYTES + P0_MEDIA_NEW_BYTES_MAX + 50

    result = build_media_download_plan(request(rows, free_local=free_local))

    assert result.report["projected_free_if_overflow_committed_bytes"] == (
        MIN_FREE_AFTER_COMMIT_BYTES - 50
    )
    assert result.report["free_space_shortfall_bytes"] == 50
    assert result.report["minimum_disk_expansion_bytes"] == 50
    assert result.report["recommended_disk_expansion_bytes"] == 5 * GIB


def test_zero_shortfall_recommends_budget_approval_not_disk_expansion() -> None:
    rows = [
        media_row(
            "selected",
            binding="a",
            owner_id="page:a",
            size=P0_MEDIA_NEW_BYTES_MAX,
            priority=1,
        ),
        media_row(
            "overflow",
            binding="b",
            owner_id="page:b",
            size=1,
            sha1=SHA1_B,
            sha256=SHA256_B,
        ),
    ]

    result = build_media_download_plan(request(rows))

    assert result.report["free_space_shortfall_bytes"] == 0
    assert result.report["recommended_disk_expansion_bytes"] == 0
    assert result.report["overflow_action_required"] == "budget_reapproval"


def test_partial_overflow_requires_new_request_and_canonical_replan() -> None:
    rows = [
        media_row(
            "selected",
            binding="a",
            owner_id="page:a",
            size=P0_MEDIA_NEW_BYTES_MAX,
            priority=1,
        ),
        media_row(
            "overflow",
            binding="b",
            owner_id="page:b",
            size=1,
            sha1=SHA1_B,
            sha256=SHA256_B,
        ),
    ]
    original = build_media_download_plan(request(rows))
    original_artifacts = original.artifact_bytes()
    subset_request = request(
        [rows[1]],
        free_local=30 * GIB,
        cloud_free=30 * GIB,
        candidate_bytes=7,
        workers=1,
    )

    partial = apply_capacity_decision(
        original,
        decision="approve_partial_overflow",
        approved_resource_ids=("overflow",),
        replan_request=subset_request,
    )

    assert partial is not original
    assert partial.allowlist_sha256 != original.allowlist_sha256
    assert [row["resource_id"] for row in partial.allowlist_rows] == ["overflow"]
    assert partial.state == "planned"
    assert partial.report["phase_overflow"] == []
    assert partial.report["selected_within_budget"] == list(partial.allowlist_rows)
    assert partial.report["capacity_totals"]["declared_bytes_total"] == 1
    assert partial.report["capacity_totals"]["selected_media_new_bytes"] == 1
    assert partial.report["capacity_totals"]["candidate_artifact_estimate_bytes"] == 7
    assert partial.report["projected_free_after_commit_bytes"] == 30 * GIB - 8
    assert partial.plan["resources"] == list(partial.allowlist_rows)
    assert partial.plan["expected_download_bytes"] == 1
    assert partial.plan["allowlist_sha256"] == partial.allowlist_sha256
    assert original.artifact_bytes() == original_artifacts


def test_partial_overflow_without_new_request_is_rejected() -> None:
    original = build_media_download_plan(
        request(
            [
                media_row("selected", binding="a", owner_id="page:a"),
                media_row(
                    "overflow",
                    binding="b",
                    owner_id="page:b",
                    size=P0_MEDIA_NEW_BYTES_MAX,
                    sha1=SHA1_B,
                    sha256=SHA256_B,
                ),
            ]
        )
    )

    with pytest.raises(ValueError, match="new planning request"):
        apply_capacity_decision(
            original,
            decision="approve_partial_overflow",
            approved_resource_ids=("overflow",),
        )


def test_partial_replan_preserves_frozen_selection_context() -> None:
    row = media_row("overflow", binding="b", owner_id="page:b")
    original = build_media_download_plan(request([row]))
    changed_context = request([row])
    object.__setattr__(
        changed_context,
        "selection_policy_sha256",
        "e" * 64,
    )

    with pytest.raises(ValueError, match="frozen planning context"):
        apply_capacity_decision(
            original,
            decision="approve_partial_overflow",
            approved_resource_ids=("overflow",),
            replan_request=changed_context,
        )


@pytest.mark.parametrize(
    ("size", "free_local"),
    [
        (P0_MEDIA_NEW_BYTES_MAX + 1, 40 * GIB),
        (1, MIN_FREE_AFTER_COMMIT_BYTES),
    ],
)
def test_partial_replan_remains_blocked_until_exact_subset_fits(
    size: int,
    free_local: int,
) -> None:
    row = media_row(
        "overflow",
        binding="b",
        owner_id="page:b",
        size=size,
    )
    original = build_media_download_plan(
        request([row])
    )
    subset_request = request([row], free_local=free_local)

    replanned = apply_capacity_decision(
        original,
        decision="approve_partial_overflow",
        approved_resource_ids=("overflow",),
        replan_request=subset_request,
    )

    assert replanned.state == "capacity_blocked"
    assert replanned.report["decision_state"] == "awaiting_explicit_approval"


@pytest.mark.parametrize(
    "decision",
    ["abandon_overflow", "expand_storage_then_replan", "defer_decision"],
)
def test_abandon_partial_expand_and_defer_are_no_write_until_new_approval(
    decision: str,
) -> None:
    original = build_media_download_plan(
        request(
            [
                media_row(
                    "selected",
                    binding="a",
                    owner_id="page:a",
                    size=P0_MEDIA_NEW_BYTES_MAX,
                    priority=1,
                ),
                media_row(
                    "overflow",
                    binding="b",
                    owner_id="page:b",
                    size=1,
                    sha1=SHA1_B,
                    sha256=SHA256_B,
                ),
            ]
        )
    )

    decided = apply_capacity_decision(original, decision=decision)

    assert decided is original
    assert original.report["decision_state"] == "awaiting_explicit_approval"


def test_budget_excluded_binding_metadata_is_preserved() -> None:
    overflow = media_row(
        "overflow",
        binding="binding:overflow",
        owner_id="page:b",
        size=1,
        sha1=SHA1_B,
        sha256=SHA256_B,
    )
    result = build_media_download_plan(
        request(
            [
                    media_row(
                        "selected",
                        binding="a",
                        owner_id="page:a",
                        size=P0_MEDIA_NEW_BYTES_MAX,
                        priority=1,
                    ),
                overflow,
            ]
        )
    )

    excluded = result.report["phase_overflow"][0]
    assert excluded["binding_ids"] == ["binding:overflow"]
    assert excluded["owner_ids"] == ["page:b"]
