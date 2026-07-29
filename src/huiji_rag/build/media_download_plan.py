from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from src.huiji_rag.build.contracts import (
    MEDIA_CAPACITY_REPORT_SCHEMA_VERSION,
    REFERENCED_MEDIA_ALLOWLIST_ENTRY_SCHEMA_VERSION,
    REFERENCED_MEDIA_PLAN_SCHEMA_VERSION,
    canonical_json_bytes,
    canonical_mapping_jsonl_bytes,
)


GIB = 1024**3
P0_MEDIA_NEW_BYTES_MAX = 268435456
P1_MEDIA_CUMULATIVE_NEW_BYTES_MAX = 2147483648
MIN_FREE_AFTER_COMMIT_BYTES = 12884901888
_P0_OWNER_TYPES = frozenset({"page", "activity", "chapter"})
_P0_EXCLUDED_ROLES = frozenset(
    {"audio", "avatar", "background", "cg", "decorative_icon"}
)
_CAPACITY_DECISIONS = frozenset(
    {
        "abandon_overflow",
        "approve_partial_overflow",
        "expand_storage_then_replan",
        "defer_decision",
    }
)
_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class MediaCapacityEvidence:
    free_local_bytes: int | None
    known_cloud_free_or_quota_bytes: int | None
    other_storage_growth_bytes: int | None
    candidate_artifact_estimate_bytes: int
    actual_free_after_commit_bytes: int | None = None
    overflow_storage_overhead_bytes: int = 0
    overflow_candidate_index_growth_bytes: int = 0


@dataclass(frozen=True)
class MediaDownloadPlanRequest:
    media_rows: tuple[Mapping[str, Any], ...]
    minio_inventory_rows: tuple[Mapping[str, Any], ...]
    source_inventory_fingerprint: str
    projection_fingerprint: str
    phase: str
    selection_policy_sha256: str
    media_budget_baseline_inventory_sha256: str
    workers: int
    capacity: MediaCapacityEvidence

    def __post_init__(self) -> None:
        object.__setattr__(self, "media_rows", tuple(self.media_rows))
        object.__setattr__(
            self, "minio_inventory_rows", tuple(self.minio_inventory_rows)
        )
        if self.phase not in {"p0", "p1"}:
            raise ValueError("media phase must be p0 or p1")
        if self.workers < 1:
            raise ValueError("media download worker count must be positive")


@dataclass(frozen=True)
class MediaDownloadPlanResult:
    state: str
    plan: Mapping[str, Any]
    allowlist_rows: tuple[Mapping[str, Any], ...]
    report: Mapping[str, Any]
    allowlist_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan", MappingProxyType(dict(self.plan)))
        object.__setattr__(
            self,
            "allowlist_rows",
            tuple(MappingProxyType(dict(row)) for row in self.allowlist_rows),
        )
        object.__setattr__(self, "report", MappingProxyType(dict(self.report)))

    def artifact_bytes(self) -> dict[str, bytes]:
        return {
            "media_capacity_report.v1.json": canonical_json_bytes(
                dict(self.report)
            ),
            "referenced_media_allowlist.v1.jsonl": (
                canonical_mapping_jsonl_bytes(self.allowlist_rows)
            ),
            "referenced_media_plan.v1.json": canonical_json_bytes(dict(self.plan)),
        }


def build_media_download_plan(
    request: MediaDownloadPlanRequest,
) -> MediaDownloadPlanResult:
    resources, not_eligible = _select_eligible_resources(request)
    baseline = _baseline_identities(request.minio_inventory_rows)
    enriched = [_with_capacity_identity(resource, baseline) for resource in resources]
    budget = (
        P0_MEDIA_NEW_BYTES_MAX
        if request.phase == "p0"
        else P1_MEDIA_CUMULATIVE_NEW_BYTES_MAX
    )
    selected, overflow = _partition_budget(enriched, budget)

    capacity = request.capacity
    disk_overflow: list[dict[str, Any]] = []
    if (
        capacity.free_local_bytes is not None
        and capacity.other_storage_growth_bytes is not None
    ):
        selected, disk_overflow = _partition_minimum_free(
            selected,
            capacity.free_local_bytes,
            capacity.other_storage_growth_bytes
            + capacity.candidate_artifact_estimate_bytes,
        )
        overflow = _merge_resources(overflow, disk_overflow)

    allowlist_rows = tuple(
        _allowlist_row(resource)
        for resource in sorted(selected, key=lambda item: str(item["resource_id"]))
    )
    allowlist_bytes = canonical_mapping_jsonl_bytes(allowlist_rows)
    allowlist_sha256 = hashlib.sha256(allowlist_bytes).hexdigest()
    totals = _capacity_totals(
        selected,
        request.workers,
        capacity.candidate_artifact_estimate_bytes,
    )
    referenced_totals = _capacity_totals(
        enriched,
        request.workers,
        capacity.candidate_artifact_estimate_bytes,
    )
    local_subtotal = (
        totals["missing_local_bytes"]
        + totals["concurrent_part_peak_bytes"]
        + totals["candidate_artifact_estimate_bytes"]
    )
    local_margin = max(2 * GIB, _twenty_percent(local_subtotal))
    cloud_margin = max(GIB, _twenty_percent(totals["MinIO_new_object_bytes"]))
    unknown_capacity = (
        capacity.free_local_bytes is None
        or capacity.known_cloud_free_or_quota_bytes is None
        or capacity.other_storage_growth_bytes is None
    )
    projected_free = (
        None
        if unknown_capacity
        else capacity.free_local_bytes
        - totals["selected_media_new_bytes"]
        - capacity.other_storage_growth_bytes
        - capacity.candidate_artifact_estimate_bytes
    )
    local_sufficient = (
        None
        if capacity.free_local_bytes is None
        else capacity.free_local_bytes >= local_subtotal + local_margin
    )
    cloud_sufficient = (
        None
        if capacity.known_cloud_free_or_quota_bytes is None
        else capacity.known_cloud_free_or_quota_bytes
        >= totals["MinIO_new_object_bytes"] + cloud_margin
    )
    threshold_sufficient = (
        None
        if projected_free is None
        else projected_free >= MIN_FREE_AFTER_COMMIT_BYTES
    )
    actual_sufficient = (
        None
        if capacity.actual_free_after_commit_bytes is None
        else capacity.actual_free_after_commit_bytes
        >= MIN_FREE_AFTER_COMMIT_BYTES
    )
    capacity_sufficient = (
        None
        if unknown_capacity
        else bool(
            local_sufficient
            and cloud_sufficient
            and threshold_sufficient
            and actual_sufficient is not False
            and not disk_overflow
        )
    )
    state = "planned"
    if overflow or capacity_sufficient is False:
        state = "capacity_blocked"
    elif unknown_capacity:
        state = "unknown_capacity"

    overflow_new_bytes = sum(int(row["new_object_bytes"]) for row in overflow)
    projected_with_overflow = (
        None
        if projected_free is None
        else projected_free
        - overflow_new_bytes
        - capacity.overflow_storage_overhead_bytes
        - capacity.overflow_candidate_index_growth_bytes
    )
    shortfall = (
        None
        if projected_with_overflow is None
        else max(0, MIN_FREE_AFTER_COMMIT_BYTES - projected_with_overflow)
    )
    recommended_expansion = (
        None
        if shortfall is None
        else 0
        if shortfall == 0
        else _round_up(
            shortfall + max(2 * GIB, _twenty_percent(overflow_new_bytes)),
            5 * GIB,
        )
    )
    selected_rows = [_evidence_row(row) for row in selected]
    overflow_rows = [_evidence_row(row) for row in overflow]
    not_eligible_rows = sorted(
        not_eligible, key=lambda item: (str(item["resource_id"]), str(item["reason_code"]))
    )
    overflow_forecast = _overflow_forecast(overflow)
    report: dict[str, Any] = {
        "schema_version": MEDIA_CAPACITY_REPORT_SCHEMA_VERSION,
        "state": state,
        "capacity_sufficient": capacity_sufficient,
        "capacity_totals": totals,
        "referenced_totals": referenced_totals,
        "local_subtotal_bytes": local_subtotal,
        "local_margin_bytes": local_margin,
        "local_required_peak_bytes": local_subtotal + local_margin,
        "cloud_margin_bytes": cloud_margin,
        "cloud_required_peak_bytes": totals["MinIO_new_object_bytes"] + cloud_margin,
        "media_budget_bytes": budget,
        "minimum_free_after_commit_bytes": MIN_FREE_AFTER_COMMIT_BYTES,
        "projected_free_after_commit_bytes": projected_free,
        "actual_free_after_commit_bytes": capacity.actual_free_after_commit_bytes,
        "selected_within_budget": selected_rows,
        "phase_overflow": overflow_rows,
        "not_eligible": not_eligible_rows,
        "budget_excluded_binding_count": sum(
            len(row["binding_ids"]) for row in overflow
        ),
        "budget_excluded_resource_count": len(overflow),
        "overflow_media_new_bytes": overflow_new_bytes,
        "overflow_forecast": overflow_forecast,
        "projected_free_if_overflow_committed_bytes": projected_with_overflow,
        "free_space_shortfall_bytes": shortfall,
        "minimum_disk_expansion_bytes": shortfall,
        "recommended_disk_expansion_bytes": recommended_expansion,
        "overflow_action_required": (
            "budget_reapproval"
            if overflow and shortfall == 0
            else "storage_expansion_or_smaller_allowlist"
            if overflow
            else None
        ),
        "decision_state": (
            "awaiting_explicit_approval" if state == "capacity_blocked" else "not_applicable"
        ),
        "allowed_decisions": sorted(_CAPACITY_DECISIONS),
    }
    plan: dict[str, Any] = {
        "schema_version": REFERENCED_MEDIA_PLAN_SCHEMA_VERSION,
        "source_inventory_fingerprint": request.source_inventory_fingerprint,
        "projection_fingerprint": request.projection_fingerprint,
        "phase": request.phase,
        "selection_policy_sha256": request.selection_policy_sha256,
        "media_budget_baseline_inventory_sha256": (
            request.media_budget_baseline_inventory_sha256
        ),
        "media_budget_bytes": budget,
        "minimum_free_after_commit_bytes": MIN_FREE_AFTER_COMMIT_BYTES,
        "workers": request.workers,
        "expected_download_bytes": sum(
            int(row["expected_download_bytes"]) for row in allowlist_rows
        ),
        "allowlist_sha256": allowlist_sha256,
        "resource_count": len(allowlist_rows),
        "binding_count": sum(len(row["binding_ids"]) for row in allowlist_rows),
        "resources": list(allowlist_rows),
        "capacity_state": state,
        "capacity_totals": totals,
    }
    return MediaDownloadPlanResult(
        state=state,
        plan=plan,
        allowlist_rows=allowlist_rows,
        report=report,
        allowlist_sha256=allowlist_sha256,
    )


def apply_capacity_decision(
    result: MediaDownloadPlanResult,
    *,
    decision: str,
    approved_resource_ids: Sequence[str] = (),
    replan_request: MediaDownloadPlanRequest | None = None,
) -> MediaDownloadPlanResult:
    if decision not in _CAPACITY_DECISIONS:
        raise ValueError("unsupported capacity decision")
    if decision != "approve_partial_overflow":
        return result
    if replan_request is None:
        raise ValueError("partial overflow approval requires a new planning request")
    frozen_context = {
        "source_inventory_fingerprint": (
            replan_request.source_inventory_fingerprint,
            result.plan["source_inventory_fingerprint"],
        ),
        "projection_fingerprint": (
            replan_request.projection_fingerprint,
            result.plan["projection_fingerprint"],
        ),
        "phase": (replan_request.phase, result.plan["phase"]),
        "selection_policy_sha256": (
            replan_request.selection_policy_sha256,
            result.plan["selection_policy_sha256"],
        ),
        "media_budget_baseline_inventory_sha256": (
            replan_request.media_budget_baseline_inventory_sha256,
            result.plan["media_budget_baseline_inventory_sha256"],
        ),
    }
    if any(actual != expected for actual, expected in frozen_context.values()):
        raise ValueError("new request changes frozen planning context")
    approved = set(approved_resource_ids)
    available_by_id = {
        str(row["resource_id"]): row
        for row in (
            *result.report["selected_within_budget"],
            *result.report["phase_overflow"],
        )
    }
    if not approved or not approved.issubset(available_by_id):
        raise ValueError("partial overflow approval must name exact planned resources")
    requested_ids = {
        str(row.get("resource_id") or "") for row in replan_request.media_rows
    }
    if requested_ids != approved:
        raise ValueError("new planning request must contain the exact approved subset")
    for row in replan_request.media_rows:
        resource_id = str(row["resource_id"])
        if _candidate_identity(row) != _candidate_identity(
            available_by_id[resource_id]
        ):
            raise ValueError("new planning request changes approved resource identity")
    replanned = build_media_download_plan(replan_request)
    replanned_ids = {
        str(row["resource_id"])
        for row in (
            *replanned.report["selected_within_budget"],
            *replanned.report["phase_overflow"],
        )
    }
    if replanned_ids != approved:
        raise ValueError("new planning request did not preserve the exact approved subset")
    return replanned


def _select_eligible_resources(
    request: MediaDownloadPlanRequest,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    identity_by_resource_id: dict[str, tuple[str, str, str, int]] = {}
    identity_by_object_key: dict[str, tuple[str, str, int]] = {}
    resource_id_by_identity: dict[tuple[str, str, str, int], str] = {}
    for source in request.media_rows:
        row = dict(source)
        if _identity_missing(row):
            excluded.append(_excluded_evidence(row, "resource_identity_incomplete"))
            continue
        identity = _validated_identity(row, label="candidate resource identity")
        resource_id = str(row["resource_id"])
        previous_identity = identity_by_resource_id.setdefault(resource_id, identity)
        if previous_identity != identity:
            raise ValueError(f"resource_id identity conflict: {resource_id}")
        object_identity = identity[1:]
        previous_object_identity = identity_by_object_key.setdefault(
            identity[0], object_identity
        )
        if previous_object_identity != object_identity:
            raise ValueError(f"object_key identity conflict: {identity[0]}")
        previous_resource_id = resource_id_by_identity.setdefault(
            identity, resource_id
        )
        if previous_resource_id != resource_id:
            raise ValueError("physical identity maps to multiple resource IDs")
        reason = _ineligible_reason(row, request.phase)
        if reason is not None:
            excluded.append(_excluded_evidence(row, reason))
        else:
            candidates.append(row)
    aggregated = _aggregate_resources(candidates)
    if request.phase == "p0":
        retained: list[dict[str, Any]] = []
        seen_owner: set[tuple[str, str]] = set()
        for row in sorted(aggregated, key=_selection_key):
            owner_keys = set(row["owner_pairs"])
            uncovered_owner_keys = owner_keys - seen_owner
            if not uncovered_owner_keys:
                excluded.append(
                    _excluded_evidence(row, "p0_owner_representative_limit")
                )
                continue
            row["representative_owner_pairs"] = sorted(uncovered_owner_keys)
            seen_owner.update(uncovered_owner_keys)
            retained.append(row)
        aggregated = retained
    else:
        for row in aggregated:
            row["representative_owner_pairs"] = sorted(row["owner_pairs"])
    return aggregated, excluded


def _ineligible_reason(row: Mapping[str, Any], phase: str) -> str | None:
    if not str(row.get("binding_id") or ""):
        return "unreferenced_resource"
    if not bool(row.get("eligible", True)):
        return "policy_not_eligible"
    role = str(row.get("media_role") or "")
    owner_type = str(row.get("owner_type") or "")
    if role == "decorative_icon":
        return "decorative_resource"
    if phase == "p0" and (
        owner_type not in _P0_OWNER_TYPES or role in _P0_EXCLUDED_ROLES
    ):
        return "p0_role_not_eligible"
    return None


def _aggregate_resources(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for source in rows:
        row = dict(source)
        identity = (
            str(row["object_key"]),
            str(row["sha1"]).lower(),
            str(row["content_sha256"]).lower(),
            int(row["size"]),
        )
        current = grouped.get(identity)
        if current is None:
            current = dict(row)
            current["binding_ids"] = set()
            current["bindings_by_id"] = {}
            current["owner_ids"] = set()
            current["owner_types"] = set()
            current["owner_pairs"] = set()
            current["media_roles"] = set()
            grouped[identity] = current
        binding_id = str(row["binding_id"])
        previous_binding = current["bindings_by_id"].get(binding_id)
        if previous_binding is not None and previous_binding != row:
            raise ValueError(f"conflicting media binding metadata: {binding_id}")
        current["bindings_by_id"][binding_id] = row
        current["binding_ids"].add(binding_id)
        owner_id = str(row["owner_id"])
        owner_type = str(row["owner_type"])
        current["owner_ids"].add(owner_id)
        current["owner_types"].add(owner_type)
        current["owner_pairs"].add((owner_type, owner_id))
        current["media_roles"].add(str(row["media_role"]))
    result: list[dict[str, Any]] = []
    for row in grouped.values():
        for field in ("binding_ids", "owner_ids", "owner_types", "media_roles"):
            row[field] = sorted(row[field])
        row["bindings"] = [
            row["bindings_by_id"][binding_id] for binding_id in row["binding_ids"]
        ]
        del row["bindings_by_id"]
        result.append(row)
    return sorted(result, key=_selection_key)


def _with_capacity_identity(
    resource: Mapping[str, Any],
    baseline: set[tuple[str, str, str, int]],
) -> dict[str, Any]:
    row = dict(resource)
    identity = (
        str(row["object_key"]),
        str(row["sha1"]).lower(),
        str(row["content_sha256"]).lower(),
        int(row["size"]),
    )
    row["minio_reused"] = identity in baseline
    row["new_object_bytes"] = 0 if row["minio_reused"] else int(row["size"])
    return row


def _baseline_identities(
    rows: Sequence[Mapping[str, Any]],
) -> set[tuple[str, str, str, int]]:
    identities: set[tuple[str, str, str, int]] = set()
    identity_by_object_key: dict[str, tuple[str, str, int]] = {}
    for row in rows:
        identity = _validated_identity(row, label="MinIO inventory identity")
        object_identity = identity[1:]
        previous = identity_by_object_key.setdefault(identity[0], object_identity)
        if previous != object_identity:
            raise ValueError(f"MinIO inventory object_key conflict: {identity[0]}")
        identities.add(identity)
    return identities


def _partition_budget(
    resources: Sequence[dict[str, Any]], budget: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    overflow: list[dict[str, Any]] = []
    used = 0
    for resource in resources:
        new_bytes = int(resource["new_object_bytes"])
        if used + new_bytes <= budget:
            selected.append(resource)
            used += new_bytes
        else:
            overflow.append(resource)
    return selected, overflow


def _partition_minimum_free(
    selected: Sequence[dict[str, Any]],
    free_bytes: int,
    known_non_media_growth_bytes: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    retained = list(selected)
    overflow: list[dict[str, Any]] = []
    while retained:
        projected = free_bytes - known_non_media_growth_bytes - sum(
            int(row["new_object_bytes"]) for row in retained
        )
        if projected >= MIN_FREE_AFTER_COMMIT_BYTES:
            break
        overflow.append(retained.pop())
    return retained, sorted(overflow, key=_selection_key)


def _capacity_totals(
    resources: Sequence[Mapping[str, Any]],
    workers: int,
    candidate_bytes: int,
) -> dict[str, int]:
    missing = [
        int(row["size"]) for row in resources if not bool(row.get("local_present"))
    ]
    selected_new = sum(int(row["new_object_bytes"]) for row in resources)
    existing_minio = sum(
        int(row["size"]) for row in resources if bool(row["minio_reused"])
    )
    new_minio = sum(
        int(row["size"]) for row in resources if not bool(row["minio_reused"])
    )
    part_peak = sum(sorted(missing, reverse=True)[:workers])
    return {
        "referenced_binding_count": sum(
            len(row["binding_ids"]) for row in resources
        ),
        "unique_resource_count": len(resources),
        "declared_bytes_total": sum(int(row["size"]) for row in resources),
        "existing_valid_local_bytes": sum(
            int(row["size"]) for row in resources if bool(row.get("local_present"))
        ),
        "missing_local_bytes": sum(missing),
        "largest_missing_resource_bytes": max(missing, default=0),
        "concurrent_part_peak_bytes": part_peak,
        "candidate_artifact_estimate_bytes": candidate_bytes,
        "MinIO_existing_object_bytes": existing_minio,
        "MinIO_new_object_bytes": new_minio,
        "selected_media_new_bytes": selected_new,
    }


def _allowlist_row(resource: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": REFERENCED_MEDIA_ALLOWLIST_ENTRY_SCHEMA_VERSION,
        "resource_id": resource["resource_id"],
        "binding_ids": list(resource["binding_ids"]),
        "bindings": [dict(binding) for binding in resource["bindings"]],
        "owner_ids": list(resource["owner_ids"]),
        "owner_types": list(resource["owner_types"]),
        "media_roles": list(resource["media_roles"]),
        "representative_owner_pairs": [
            list(pair) for pair in resource["representative_owner_pairs"]
        ],
        "name": resource["filename"],
        "filename": resource["filename"],
        "url": resource["url"],
        "mime": resource.get("mime"),
        "sha1": str(resource["sha1"]).lower(),
        "content_sha256": str(resource["content_sha256"]).lower(),
        "size": int(resource["size"]),
        "local_relpath": resource["local_relpath"],
        "object_key": resource["object_key"],
        "download_status": resource.get("download_status"),
        "expected_download_bytes": (
            0 if bool(resource.get("local_present")) else int(resource["size"])
        ),
        "new_object_bytes": int(resource["new_object_bytes"]),
    }


def _evidence_row(resource: Mapping[str, Any]) -> dict[str, Any]:
    return _allowlist_row(resource)


def _excluded_evidence(
    row: Mapping[str, Any], reason_code: str
) -> dict[str, Any]:
    binding_ids = row.get("binding_ids")
    bindings = row.get("bindings")
    owner_ids = row.get("owner_ids")
    owner_types = row.get("owner_types")
    media_roles = row.get("media_roles")
    return {
        "resource_id": str(row.get("resource_id") or ""),
        "binding_ids": (
            list(binding_ids)
            if isinstance(binding_ids, list)
            else sorted({str(row.get("binding_id") or "")} - {""})
        ),
        "bindings": (
            [dict(binding) for binding in bindings]
            if isinstance(bindings, list)
            else [dict(row)] if row.get("binding_id") else []
        ),
        "owner_ids": (
            list(owner_ids)
            if isinstance(owner_ids, list)
            else sorted({str(row.get("owner_id") or "")} - {""})
        ),
        "owner_types": (
            list(owner_types)
            if isinstance(owner_types, list)
            else sorted({str(row.get("owner_type") or "")} - {""})
        ),
        "media_roles": (
            list(media_roles)
            if isinstance(media_roles, list)
            else sorted({str(row.get("media_role") or "")} - {""})
        ),
        "reason_code": reason_code,
    }


def _overflow_forecast(
    resources: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    by_owner_type: dict[str, dict[str, Any]] = {}
    by_priority: dict[str, dict[str, Any]] = {}
    for resource in resources:
        for owner_type in resource["owner_types"]:
            group = by_owner_type.setdefault(
                str(owner_type), {"binding_ids": set(), "resource_ids": set()}
            )
            group["binding_ids"].update(resource["binding_ids"])
            group["resource_ids"].add(str(resource["resource_id"]))
        priority_key = str(resource.get("media_role") or "representative")
        group = by_priority.setdefault(
            priority_key, {"binding_ids": set(), "resource_ids": set()}
        )
        group["binding_ids"].update(resource["binding_ids"])
        group["resource_ids"].add(str(resource["resource_id"]))
    return {
        "resource_count": len(resources),
        "binding_count": sum(len(row["binding_ids"]) for row in resources),
        "new_object_bytes": sum(int(row["new_object_bytes"]) for row in resources),
        "reused_object_bytes": sum(
            int(row["size"]) for row in resources if bool(row["minio_reused"])
        ),
        "largest_resource_bytes": max(
            (int(row["size"]) for row in resources), default=0
        ),
        "concurrent_part_peak_bytes": max(
            (int(row["size"]) for row in resources), default=0
        ),
        "by_owner_type": _group_counts(by_owner_type),
        "by_priority": _group_counts(by_priority),
    }


def _group_counts(groups: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    return {
        key: {
            "binding_count": len(value["binding_ids"]),
            "resource_count": len(value["resource_ids"]),
        }
        for key, value in sorted(groups.items())
    }


def _merge_resources(
    first: Sequence[dict[str, Any]], second: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_resource = {
        str(row["resource_id"]): row for row in (*first, *second)
    }
    return sorted(by_resource.values(), key=_selection_key)


def _selection_key(row: Mapping[str, Any]) -> tuple[int, str]:
    return int(row.get("selection_priority") or 0), str(row.get("resource_id") or "")


def _twenty_percent(value: int) -> int:
    return (value + 4) // 5


def _round_up(value: int, quantum: int) -> int:
    return ((value + quantum - 1) // quantum) * quantum


def _identity_missing(row: Mapping[str, Any]) -> bool:
    required = (
        "resource_id",
        "filename",
        "url",
        "sha1",
        "content_sha256",
        "size",
        "local_relpath",
        "object_key",
    )
    return any(row.get(field) in {None, ""} for field in required)


def _candidate_identity(row: Mapping[str, Any]) -> tuple[str, str, str, int]:
    return (
        str(row["object_key"]),
        str(row["sha1"]),
        str(row["content_sha256"]),
        int(row["size"]),
    )


def _validated_identity(
    row: Mapping[str, Any],
    *,
    label: str,
) -> tuple[str, str, str, int]:
    try:
        object_key = row["object_key"]
        sha1 = row["sha1"]
        sha256 = row["content_sha256"]
        raw_size = row["size"]
        if (
            not isinstance(object_key, str)
            or not isinstance(sha1, str)
            or not isinstance(sha256, str)
            or not isinstance(raw_size, int)
            or isinstance(raw_size, bool)
        ):
            raise ValueError
        size = raw_size
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"{label} is incomplete or malformed") from error
    if (
        not object_key
        or not _SHA1_RE.fullmatch(sha1)
        or not _SHA256_RE.fullmatch(sha256)
        or size < 0
    ):
        raise ValueError(f"{label} is incomplete or malformed")
    return object_key, sha1, sha256, size
