"""Source-budget calculations for composed retrieval policies."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.rag.contracts import EntityRef
from src.rag.ownership import filter_owned_rows
from src.rag.packet_policy import IntentPolicyBundle


@dataclass(frozen=True)
class IntentCoverage:
    intent: str
    available: int
    target: int
    retained: int
    shortfall: int


@dataclass(frozen=True)
class AllocationResult:
    sources: list[dict[str, object]]
    omitted_rows: list[dict[str, object]]
    coverage: tuple[IntentCoverage, ...]
    chars_used: int


def _available_row_count(rows: Any) -> int:
    if rows is None:
        return 0
    if isinstance(rows, int):
        return max(0, rows)
    try:
        return len(rows)
    except TypeError:
        return sum(1 for _ in rows)


def clamp_voice_page_size(voice_page_size: int, voice_page_size_max: int) -> int:
    maximum = max(1, int(voice_page_size_max))
    return min(maximum, max(1, int(voice_page_size)))


def calculate_required_source_count(
    bundle: IntentPolicyBundle,
    exact_rows_by_intent: Mapping[str, Any],
    voice_page_size: int,
) -> int:
    """Return the source quota implied by exact text rows for each intent."""
    required = 0
    for intent, policy in zip(bundle.requested_intents, bundle.policies):
        available = _available_row_count(exact_rows_by_intent.get(intent))
        if policy.coverage_mode == "all_available":
            required += available
        elif policy.coverage_mode == "fixed":
            target = policy.source_target
            if intent == "voice":
                target = min(target, clamp_voice_page_size(voice_page_size, target))
            required += min(target, available)
        else:
            required += min(1, available)
    return required


def calculate_candidate_k(
    configured_k: int,
    required_source_count: int,
    oversample: int,
    hard_max: int,
) -> int:
    return min(hard_max, max(configured_k, oversample * required_source_count))


def _child_id(row: Mapping[str, Any]) -> str:
    return str(row.get("child_id") or row.get("id") or "")


def _text_length(row: Mapping[str, Any]) -> int:
    return len(str(row.get("text") or row.get("content") or ""))


def _matched_intents(row: Mapping[str, Any]) -> tuple[str, ...]:
    value = row.get("matched_intents", ())
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item) for item in value if str(item))
    return ()


def _merge_rows(
    ranked_rows: Any,
    exact_rows_by_intent: Mapping[str, Any],
    requested_intents: tuple[str, ...],
) -> tuple[list[dict[str, object]], dict[str, set[str]]]:
    merged: dict[str, dict[str, object]] = {}
    intent_sets: dict[str, set[str]] = {}
    exact_ids: dict[str, set[str]] = {intent: set() for intent in requested_intents}

    def add(row: Mapping[str, Any], exact_intent: str | None = None) -> None:
        child_id = _child_id(row)
        if not child_id:
            return
        if child_id not in merged:
            merged[child_id] = dict(row)
            intent_sets[child_id] = set()
        else:
            current = merged[child_id]
            for key, value in row.items():
                if key not in current or current[key] in (None, "", (), []):
                    current[key] = value
        intent_sets[child_id].update(_matched_intents(row))
        if exact_intent:
            intent_sets[child_id].add(exact_intent)
            exact_ids.setdefault(exact_intent, set()).add(child_id)

    for row in ranked_rows or ():
        add(row)
    for intent in requested_intents:
        for row in exact_rows_by_intent.get(intent) or ():
            add(row, intent)

    requested_order = {intent: index for index, intent in enumerate(requested_intents)}
    rows = list(merged.values())
    for row in rows:
        child_id = _child_id(row)
        row["matched_intents"] = tuple(
            sorted(
                intent_sets[child_id],
                key=lambda intent: (requested_order.get(intent, len(requested_order)), intent),
            )
        )
    rows.sort(
        key=lambda row: (
            0,
            int(row.get("expansion_position", 0) or 0),
            _child_id(row),
            str(row.get("parent_id") or ""),
        )
        if int(row.get("expansion_position", 0) or 0) > 0
        else (
            1,
            -float(row.get("score", 0.0) or 0.0),
            _child_id(row),
            str(row.get("parent_id") or ""),
        )
    )
    return rows, exact_ids


def _quota_contribution(
    row: Mapping[str, Any],
    intent: str,
    coverage_mode: str,
    exact_ids: Mapping[str, set[str]],
) -> int:
    if coverage_mode == "all_available":
        return int(_child_id(row) in exact_ids.get(intent, set()))
    return int(intent in _matched_intents(row))


def _select_quota_row_indices(
    rows: list[dict[str, object]],
    requested: tuple[str, ...],
    policies: Mapping[str, Any],
    targets: Mapping[str, int],
    exact_ids: Mapping[str, set[str]],
    *,
    source_limit: int,
    char_limit: int,
) -> tuple[int, ...]:
    """Find a deterministic feasible quota set within the bounded retrieval budget."""
    target_vector = tuple(min(targets[intent], source_limit) for intent in requested)
    zero_coverage = tuple(0 for _ in requested)
    voice_index = requested.index("voice") if "voice" in requested else None
    count_limit = min(source_limit, sum(target_vector))

    def contributions_for(row: Mapping[str, Any]) -> tuple[int, ...]:
        return tuple(
            _quota_contribution(
                row,
                intent,
                policies[intent].coverage_mode,
                exact_ids,
            )
            for intent in requested
        )

    def advance_coverage(
        coverage: tuple[int, ...],
        contributions: tuple[int, ...],
    ) -> tuple[int, ...]:
        return tuple(
            min(target, current + contribution)
            for target, current, contribution in zip(
                target_vector, coverage, contributions
            )
        )

    # Preserve ranked precedence whenever the ranked path itself is feasible.
    ranked_coverage = zero_coverage
    ranked_chars = 0
    ranked_indices: tuple[int, ...] = ()
    for row_index, row in enumerate(rows):
        contributions = contributions_for(row)
        next_coverage = advance_coverage(ranked_coverage, contributions)
        if next_coverage == ranked_coverage:
            continue
        row_chars = _text_length(row)
        if len(ranked_indices) >= count_limit or ranked_chars + row_chars > char_limit:
            continue
        if (
            voice_index is not None
            and "voice" in _matched_intents(row)
            and ranked_coverage[voice_index] >= target_vector[voice_index]
        ):
            continue
        ranked_coverage = next_coverage
        ranked_chars += row_chars
        ranked_indices = (*ranked_indices, row_index)
        if ranked_coverage == target_vector:
            return ranked_indices

    # For identical bounded coverage and count, minimum characters dominates all
    # future feasibility; ranked indices deterministically break equal-cost ties.
    states: dict[
        tuple[tuple[int, ...], int],
        tuple[int, tuple[int, ...]],
    ] = {(zero_coverage, 0): (0, ())}

    for row_index, row in enumerate(rows):
        contributions = contributions_for(row)
        if not any(contributions):
            continue
        row_chars = _text_length(row)
        updates: dict[
            tuple[tuple[int, ...], int],
            tuple[int, tuple[int, ...]],
        ] = {}
        for (coverage, count), (used_chars, indices) in list(states.items()):
            if count >= count_limit or used_chars + row_chars > char_limit:
                continue
            if (
                voice_index is not None
                and "voice" in _matched_intents(row)
                and coverage[voice_index] >= target_vector[voice_index]
            ):
                continue
            next_coverage = advance_coverage(coverage, contributions)
            if next_coverage == coverage:
                continue
            key = (next_coverage, count + 1)
            candidate = (used_chars + row_chars, (*indices, row_index))
            existing = updates.get(key, states.get(key))
            if existing is None or candidate < existing:
                updates[key] = candidate
        states.update(updates)

    complete = [
        (count, value)
        for (coverage, count), value in states.items()
        if coverage == target_vector
    ]
    if complete:
        _, (_, indices) = min(
            complete,
            key=lambda item: (item[1][1], item[1][0], item[0]),
        )
        return indices

    def fallback_key(
        item: tuple[
            tuple[tuple[int, ...], int],
            tuple[int, tuple[int, ...]],
        ]
    ) -> tuple[Any, ...]:
        (coverage, count), (used_chars, indices) = item
        represented = sum(value > 0 for value in coverage)
        satisfied = sum(value >= target for value, target in zip(coverage, target_vector))
        return (-represented, -satisfied, -sum(coverage), indices, used_chars, count)

    (_, _), (_, indices) = min(states.items(), key=fallback_key)
    return indices


def allocate_sources(
    ranked_rows: Any,
    exact_rows_by_intent: Mapping[str, Any],
    bundle: IntentPolicyBundle,
    *,
    max_sources: int,
    context_budget_chars: int,
    voice_page_size: int,
    owner: EntityRef | None = None,
) -> AllocationResult:
    """Allocate final text rows without allowing score-only truncation to erase an intent."""
    owned_ranked, _ = filter_owned_rows(ranked_rows or (), owner, "allocate.ranked")
    owned_exact: dict[str, list[dict[str, object]]] = {}
    for intent in bundle.requested_intents:
        owned_exact[intent], _ = filter_owned_rows(
            exact_rows_by_intent.get(intent) or (),
            owner,
            f"allocate.exact.{intent}",
        )
    rows, exact_ids = _merge_rows(owned_ranked, owned_exact, bundle.requested_intents)
    requested = bundle.requested_intents
    policies = dict(zip(requested, bundle.policies))
    candidates = {
        intent: [row for row in rows if intent in _matched_intents(row)]
        for intent in requested
    }
    targets: dict[str, int] = {}
    for intent in requested:
        policy = policies[intent]
        if policy.coverage_mode == "all_available":
            targets[intent] = max(1, len(exact_ids.get(intent, ())))
        elif policy.coverage_mode == "fixed":
            target = max(1, int(policy.source_target))
            if intent == "voice":
                target = min(target, max(1, int(voice_page_size)))
            targets[intent] = target
        else:
            targets[intent] = max(1, int(policy.source_target))

    source_limit = max(0, int(max_sources))
    char_limit = max(0, int(context_budget_chars))
    selected: list[dict[str, object]] = []
    selected_ids: set[str] = set()
    chars_used = 0

    def quota_retained_count(intent: str) -> int:
        return sum(
            _quota_contribution(
                row,
                intent,
                policies[intent].coverage_mode,
                exact_ids,
            )
            for row in selected
        )

    def matched_retained_count(intent: str) -> int:
        return sum(intent in _matched_intents(row) for row in selected)

    def can_add(row: Mapping[str, Any]) -> bool:
        if _child_id(row) in selected_ids or len(selected) >= source_limit:
            return False
        if (
            "voice" in _matched_intents(row)
            and matched_retained_count("voice") >= targets.get("voice", 0)
        ):
            return False
        return chars_used + _text_length(row) <= char_limit

    def add(row: dict[str, object]) -> bool:
        nonlocal chars_used
        if not can_add(row):
            return False
        selected.append(row)
        selected_ids.add(_child_id(row))
        chars_used += _text_length(row)
        return True

    quota_indices = _select_quota_row_indices(
        rows,
        requested,
        policies,
        targets,
        exact_ids,
        source_limit=source_limit,
        char_limit=char_limit,
    )
    quota_ids = {_child_id(rows[index]) for index in quota_indices}

    def add_quota(row: dict[str, object]) -> None:
        nonlocal chars_used
        child_id = _child_id(row)
        if child_id in selected_ids:
            return
        selected.append(row)
        selected_ids.add(child_id)
        chars_used += _text_length(row)

    # Emit one selected quota row per requested intent before quota completion.
    for intent in requested:
        if quota_retained_count(intent):
            continue
        for row in rows:
            if (
                _child_id(row) in quota_ids
                and _quota_contribution(
                    row,
                    intent,
                    policies[intent].coverage_mode,
                    exact_ids,
                )
            ):
                add_quota(row)
                break

    # Complete quotas in requested-intent order using the feasible selected set.
    for intent in requested:
        for row in rows:
            if quota_retained_count(intent) >= targets[intent]:
                break
            if (
                _child_id(row) in quota_ids
                and _quota_contribution(
                    row,
                    intent,
                    policies[intent].coverage_mode,
                    exact_ids,
                )
            ):
                add_quota(row)

    for row in rows:
        if _child_id(row) in quota_ids:
            add_quota(row)

    # Only the remaining capacity is score-driven. Voice text stays page-size bounded.
    requested_set = set(requested)
    for row in rows:
        if requested_set.intersection(_matched_intents(row)):
            add(row)

    coverage = tuple(
        IntentCoverage(
            intent=intent,
            available=len(candidates[intent]),
            target=targets[intent],
            retained=quota_retained_count(intent),
            shortfall=max(0, targets[intent] - quota_retained_count(intent)),
        )
        for intent in requested
    )
    omitted = [row for row in rows if _child_id(row) not in selected_ids]
    return AllocationResult(
        sources=selected,
        omitted_rows=omitted,
        coverage=coverage,
        chars_used=chars_used,
    )
