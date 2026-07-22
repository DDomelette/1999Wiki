from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from src.rag.contracts import EntityRef
from src.rag.ownership import filter_owned_rows
from src.rag.packet_policy import PacketPolicy


@dataclass(frozen=True)
class ExpansionResult:
    sources: list[dict[str, Any]]
    omitted_actions: list[dict[str, Any]]
    debug: dict[str, Any]


SECTION_ORDER = {
    "profile": 10,
    "dossier": 20,
    "collection": 30,
    "culture": 30,
    "skill": 40,
    "skills": 40,
    "culture_dossier": 50,
    "item": 50,
    "items": 50,
    "media": 60,
    "skin": 65,
    "skins": 65,
    "udimo": 70,
    "voice": 80,
}

PARENT_TO_INTENT = {
    "profile": "profile_fact",
    "dossier": "profile_fact",
    "collection": "item",
    "culture": "item",
    "skills": "skill",
    "culture_dossier": "culture",
    "items": "culture",
    "media": "media",
    "skins": "media",
    "udimo": "udimo",
    "voice": "voice",
}

PARENT_LABELS = {
    "profile": "基础资料",
    "dossier": "档案",
    "collection": "全部单品",
    "culture": "全部单品",
    "skills": "全部技能",
    "culture_dossier": "文化档案",
    "items": "文化档案",
    "media": "立绘/媒体",
    "skins": "皮肤",
    "udimo": "尤提姆",
    "voice": "语音",
}


def _section_from_parent(parent_id: str) -> str:
    return parent_id.rsplit("/", 1)[-1] if "/" in parent_id else parent_id


def _section_key(row: dict[str, Any]) -> str:
    return str(row.get("section_kind") or _section_from_parent(str(row.get("parent_id", ""))))


def _normalized_section(row: dict[str, Any]) -> str:
    section = _section_key(row)
    return {
        "skill": "skills",
        "item": "items",
        "skin": "skins",
    }.get(section, section)


def _row_id(row: dict[str, Any]) -> str:
    return str(row.get("child_id") or row.get("id") or "")


def _text_len(row: dict[str, Any]) -> int:
    return len(str(row.get("text") or row.get("content") or ""))


def _same_entity(row: dict[str, Any], entity_name: str) -> bool:
    return bool(entity_name) and str(row.get("entity_name") or row.get("name") or "") == entity_name


def _make_action(
    row: dict[str, Any],
    entity_name: str,
    owner: EntityRef | None,
    semantic_intents: Iterable[str],
) -> dict[str, Any]:
    parent_id = str(row.get("parent_id", ""))
    parent_section = _section_from_parent(parent_id)
    intent = PARENT_TO_INTENT.get(parent_section, _section_key(row))
    label = PARENT_LABELS.get(parent_section) or str(row.get("title") or row.get("section_kind") or "更多")
    query = f"介绍{entity_name}的{label}" if entity_name else f"查看{label}"
    return {
        "label": label,
        "query": query,
        "action_type": "expand_parent",
        "entity": entity_name,
        "entity_type": owner.entity_type if owner else str(row.get("entity_type") or ""),
        "entity_id": owner.entity_id if owner else str(row.get("entity_id") or ""),
        "semantic_intents": list(dict.fromkeys(str(item) for item in semantic_intents if str(item))),
        "intent": intent,
        "packet_policy": "section_detail",
        "target_parent_id": parent_id,
    }


def make_omitted_actions(
    rows: list[dict[str, Any]],
    entity_name: str,
    owner: EntityRef | None = None,
    semantic_intents: Iterable[str] = (),
) -> list[dict[str, Any]]:
    omitted_by_parent: dict[str, dict[str, Any]] = {}
    ordered_rows = sorted(
        rows,
        key=lambda row: (
            SECTION_ORDER.get(_normalized_section(row), 999),
            str(row.get("parent_id", "")),
            _row_id(row),
        ),
    )
    for row in ordered_rows:
        parent_id = str(row.get("parent_id", ""))
        if parent_id and parent_id not in omitted_by_parent:
            omitted_by_parent[parent_id] = _make_action(
                row,
                entity_name,
                owner,
                semantic_intents,
            )
    return list(omitted_by_parent.values())


def expand_ranked_children(
    ranked: list[dict[str, Any]],
    all_children: list[dict[str, Any]],
    policy: PacketPolicy,
    budget_chars: int,
    sibling_window: int = 1,
    owner: EntityRef | None = None,
    semantic_intents: Iterable[str] = (),
) -> ExpansionResult:
    ranked, ranked_ownership = filter_owned_rows(ranked, owner, "expand.ranked")
    all_children, child_ownership = filter_owned_rows(
        all_children,
        owner,
        "expand.children",
    )
    if not ranked:
        return ExpansionResult(
            sources=[],
            omitted_actions=[],
            debug={
                "reason": "empty_ranked",
                "owner_mismatch": ranked_ownership.owner_mismatch + child_ownership.owner_mismatch,
                "missing_owner_metadata": (
                    ranked_ownership.missing_owner_metadata
                    + child_ownership.missing_owner_metadata
                ),
            },
        )

    entity_name = owner.entity_name if owner else str(
        ranked[0].get("entity_name") or ranked[0].get("name") or ""
    )
    ranked_ids = {_row_id(row) for row in ranked}
    by_parent: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    by_id: dict[str, dict[str, Any]] = {}
    for child in all_children:
        row = dict(child)
        child_id = _row_id(row)
        if not child_id:
            continue
        by_id[child_id] = row
        by_parent[str(row.get("parent_id", ""))].append(row)
    for rows in by_parent.values():
        rows.sort(key=lambda item: int(item.get("chunk_index", 0) or 0))

    candidate_ids: set[str] = set()
    selected_parent_ids = {str(row.get("parent_id", "")) for row in ranked if row.get("parent_id")}
    policy_sections = set(policy.sections)

    for child in all_children:
        if entity_name and not _same_entity(child, entity_name):
            continue
        parent_section = _section_from_parent(str(child.get("parent_id", "")))
        section = _section_key(child)
        if _row_id(child) in ranked_ids or parent_section in policy_sections or section in policy_sections:
            candidate_ids.add(_row_id(child))
            selected_parent_ids.add(str(child.get("parent_id", "")))

    for hit in ranked:
        hit_id = _row_id(hit)
        parent_id = str(hit.get("parent_id", ""))
        rows = by_parent.get(parent_id, [])
        positions = {_row_id(row): idx for idx, row in enumerate(rows)}
        if hit_id not in positions:
            candidate_ids.add(hit_id)
            continue
        pos = positions[hit_id]
        for idx in range(max(0, pos - sibling_window), min(len(rows), pos + sibling_window + 1)):
            candidate_ids.add(_row_id(rows[idx]))

    candidates: list[dict[str, Any]] = []
    ranked_by_id = {_row_id(row): row for row in ranked}
    ranked_positions = {_row_id(row): position for position, row in enumerate(ranked, start=1)}
    ranked_scores = {child_id: float(row.get("score", 0.0)) for child_id, row in ranked_by_id.items()}
    for child_id in sorted(candidate_ids):
        row = dict(by_id.get(child_id) or next((item for item in ranked if _row_id(item) == child_id), {}))
        if not row:
            continue
        ranked_row = ranked_by_id.get(child_id, {})
        if ranked_row.get("matched_intents"):
            row["matched_intents"] = tuple(ranked_row["matched_intents"])
        if child_id in ranked_scores:
            row["score"] = ranked_scores[child_id]
            row["ranked_position"] = ranked_positions[child_id]
        else:
            row.setdefault("score", float(row.get("score", 0.0)))
        ranked_debug = ranked_by_id.get(child_id, {}).get("debug", {})
        debug = dict(ranked_debug if isinstance(ranked_debug, dict) else {})
        debug.update(row.get("debug", {}) if isinstance(row.get("debug"), dict) else {})
        if child_id in ranked_scores:
            debug["layered_hit"] = True
            debug["ranked_position"] = ranked_positions[child_id]
        row["debug"] = debug
        candidates.append(row)

    def policy_rank(row: dict[str, Any]) -> int:
        if not policy.sections or policy.name == "intro_full":
            return 0
        parent_section = _section_from_parent(str(row.get("parent_id", "")))
        section = _section_key(row)
        normalized = _normalized_section(row)
        for idx, wanted in enumerate(policy.sections):
            if wanted in {parent_section, section, normalized}:
                return idx
        return len(policy.sections) + 1

    def sort_key(row: dict[str, Any]) -> tuple[int, int, int, float, int, str, str]:
        ranked_position = int(row.get("ranked_position", 0) or 0)
        if ranked_position:
            return (
                0,
                ranked_position,
                0,
                0.0,
                0,
                _row_id(row),
                str(row.get("parent_id") or ""),
            )
        section = _section_key(row)
        return (
            1,
            policy_rank(row),
            SECTION_ORDER.get(section, 999),
            -float(row.get("score", 0.0)),
            int(row.get("chunk_index", 0) or 0),
            _row_id(row),
            str(row.get("parent_id") or ""),
        )

    retained: list[dict[str, Any]] = []
    used_chars = 0
    ordered_candidates = sorted(candidates, key=sort_key)
    for expansion_position, row in enumerate(ordered_candidates, start=1):
        row["expansion_position"] = expansion_position
        length = _text_len(row)
        if retained and budget_chars > 0 and used_chars + length > budget_chars:
            continue
        retained.append(row)
        used_chars += length

    retained_ids = {_row_id(row) for row in retained}
    omitted_rows = [row for row in candidates if _row_id(row) not in retained_ids]

    return ExpansionResult(
        sources=retained,
        omitted_actions=make_omitted_actions(
            omitted_rows,
            entity_name,
            owner,
            semantic_intents,
        ),
        debug={
            "candidate_count": len(candidates),
            "retained_count": len(retained),
            "used_chars": used_chars,
            "selected_parent_ids": sorted(pid for pid in selected_parent_ids if pid),
            "owner_mismatch": ranked_ownership.owner_mismatch + child_ownership.owner_mismatch,
            "missing_owner_metadata": (
                ranked_ownership.missing_owner_metadata
                + child_ownership.missing_owner_metadata
            ),
        },
    )
