from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any
import json


def _quality_flags(row: dict[str, Any]) -> set[str]:
    raw = row.get("quality_flags", ())
    if isinstance(raw, str):
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, list):
                return {str(item) for item in loaded}
        except json.JSONDecodeError:
            return {item.strip() for item in raw.split(",") if item.strip()}
    if isinstance(raw, (list, tuple, set)):
        return {str(item) for item in raw}
    return set()


def _is_hard_excluded(row: dict[str, Any]) -> bool:
    if "entity_name" not in row and "name" not in row:
        return False
    return str(row.get("entity_name", row.get("name", ""))).strip() in {"", "???", "？??", "？？？"}


def weighted_rrf(
    bm25: list[dict[str, Any]],
    dense: list[dict[str, Any]],
    entity: str | None,
    intent: str,
    k: int = 60,
    w_bm25: float = 1.2,
    w_dense: float = 1.0,
    allow_youtium: bool = False,
    semantic_intents: Iterable[str] = (),
    intent_sections: Mapping[str, tuple[str, ...]] | None = None,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    scores: defaultdict[str, float] = defaultdict(float)
    debug: defaultdict[str, dict[str, Any]] = defaultdict(dict)

    for rank, row in enumerate(bm25, start=1):
        if _is_hard_excluded(row):
            continue
        key = str(row["child_id"])
        merged.setdefault(key, dict(row))
        scores[key] += w_bm25 / (k + rank)
        debug[key]["bm25_rank"] = rank

    for rank, row in enumerate(dense, start=1):
        if _is_hard_excluded(row):
            continue
        key = str(row["child_id"])
        merged.setdefault(key, dict(row))
        scores[key] += w_dense / (k + rank)
        debug[key]["dense_rank"] = rank

    intents = tuple(dict.fromkeys((intent, *(str(value) for value in semantic_intents))))
    default_sections = {
        "skill": ("skill", "skills"),
        "item": ("collection",),
        "culture": ("culture_dossier",),
        "udimo": ("udimo",),
        "voice": ("voice",),
        "media": ("media", "skin", "skins", "profile"),
        "video": ("media",),
    }

    for key, row in merged.items():
        if entity and str(row.get("entity_name", "")) == entity:
            scores[key] += 0.30
            debug[key]["exact_entity_bonus"] = 0.30
        section = str(row.get("section_kind", ""))
        parent_section = str(row.get("parent_id", "")).rsplit("/", 1)[-1]
        matching_intents = [
            semantic_intent
            for semantic_intent in intents
            if section in (intent_sections or {}).get(
                semantic_intent,
                default_sections.get(semantic_intent, ()),
            )
            or parent_section in (intent_sections or {}).get(
                semantic_intent,
                default_sections.get(semantic_intent, ()),
            )
        ]
        if matching_intents:
            scores[key] += 0.25
            debug[key]["intent_section_bonus"] = 0.25
            debug[key]["intent_section_matches"] = matching_intents
        if any(value in {"profile", "profile_fact", "intro"} for value in intents):
            if str(row.get("category", "")) == "character" and str(row.get("section_kind", "")) == "profile":
                scores[key] += 0.35
                debug[key]["profile_section_bonus"] = 0.35
            elif str(row.get("category", "")) != "character":
                scores[key] -= 0.20
                debug[key]["non_character_profile_penalty"] = -0.20
            elif str(row.get("section_kind", "")) == "skill" and any(
                value in {"profile", "profile_fact"} for value in intents
            ):
                scores[key] -= 0.08
                debug[key]["profile_skill_penalty"] = -0.08
        flags = _quality_flags(row)
        for flag, penalty in {
            "weak_entity_name": -0.50,
            "raw_html_noise": -0.20,
            "short_text": -0.05,
            "missing_media": -0.05,
        }.items():
            if flag in flags:
                scores[key] += penalty
                debug[key][f"quality_{flag}_penalty"] = penalty
        if not {"item", "udimo"}.intersection(intents) and not allow_youtium:
            haystack = " ".join(
                str(row.get(field, "")) for field in ("entity_name", "text", "search_text", "title")
            )
            if str(row.get("category", "")) == "item" and ("尤提姆" in haystack or "youtium" in haystack.lower()):
                scores[key] -= 0.35
                debug[key]["youtium_penalty"] = -0.35
        row["score"] = scores[key]
        row["debug"] = dict(debug[key])

    return sorted(
        merged.values(),
        key=lambda item: (
            -float(item["score"]),
            str(item.get("child_id") or item.get("id") or ""),
            str(item.get("parent_id") or ""),
        ),
    )


def rerank_children_with_parent_context(
    ranked: list[dict[str, Any]],
    all_children: list[dict[str, Any]],
    neighbor_window: int = 1,
    limit: int = 20,
) -> list[dict[str, Any]]:
    by_parent: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for child in all_children:
        by_parent[str(child.get("parent_id", ""))].append(child)
    for rows in by_parent.values():
        rows.sort(key=lambda item: int(item.get("chunk_index", 0) or 0))

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for hit in ranked:
        hit_id = str(hit["child_id"])
        parent_id = str(hit.get("parent_id", ""))
        parent_rows = by_parent.get(parent_id, [])
        positions = {str(row.get("child_id")): idx for idx, row in enumerate(parent_rows)}
        candidate_indices = [positions[hit_id]] if hit_id in positions else []
        for pos in list(candidate_indices):
            candidate_indices.extend(
                range(max(0, pos - neighbor_window), min(len(parent_rows), pos + neighbor_window + 1))
            )
        for idx in candidate_indices:
            row = dict(parent_rows[idx])
            row.setdefault("score", hit.get("score", 0.0))
            row.setdefault("debug", hit.get("debug", {}))
            child_id = str(row.get("child_id"))
            if child_id not in seen:
                seen.add(child_id)
                out.append(row)
            if len(out) >= limit:
                return out
    return out
