"""Stage 2 robust intent routing, section reranking, and context packing."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any
import json
import urllib.request

from src.rag.entity_packet import RetrievalCandidate
from src.rag.query_plan import INTENT_SECTION_HINTS, QueryPlan


class SiliconFlowRerankClient:
    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def score(self, query: str, documents: list[str]) -> list[float]:
        payload = json.dumps(
            {
                "model": self.model,
                "query": query,
                "documents": documents,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/rerank",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
        results = data.get("results") or data.get("data") or []
        scores = [0.0 for _ in documents]
        for index, item in enumerate(results):
            target_index = int(item.get("index", index))
            if 0 <= target_index < len(scores):
                scores[target_index] = float(item.get("relevance_score", item.get("score", 0.0)))
        return scores


class OptionalBgeReranker:
    def __init__(
        self,
        enabled: bool,
        base_url: str,
        api_key: str,
        model: str,
        client: Any | None = None,
    ) -> None:
        self.enabled = enabled
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.client = client or SiliconFlowRerankClient(base_url, api_key, model)

    def rerank(self, query: str, rows: list[dict[str, Any]], limit: int | None = None) -> list[dict[str, Any]]:
        if not self.enabled or not rows:
            return rows[:limit] if limit else rows
        documents = [str(row.get("text") or row.get("search_text") or row.get("content") or "") for row in rows]
        scores = self.client.score(query, documents)
        scored: list[dict[str, Any]] = []
        for row, score in zip(rows, scores):
            item = dict(row)
            debug = dict(item.get("debug", {}))
            debug["reranker_score"] = float(score)
            item["debug"] = debug
            item["score"] = float(item.get("score", 0.0)) + float(score)
            scored.append(item)
        scored.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
        return scored[:limit] if limit else scored


NOISE_HEADINGS = ("语音", "单品", "箱中日历")
INTENT_QUERY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "intro": ("介绍", "讲讲", "是谁", "概览", "简介", "说说", "了解"),
    "profile_fact": ("基础", "生日", "属性", "星级", "稀有度", "职业", "定位", "伤害类型", "资料"),
    "skill": ("技能", "神秘术", "大招", "至终", "仪式", "传承", "洞悉", "塑造"),
    "item": ("单品", "物品", "材料", "道具", "尤提姆"),
    "culture": ("文化", "背景", "设定", "考据", "出处"),
    "voice": ("语音", "台词", "互动", "对白"),
    "media": ("图片", "立绘", "头像", "皮肤", "图像", "看图"),
    "video": ("视频", "PV", "动画", "演示"),
    "psychube": ("心相", "搭配", "推荐"),
    "story": ("剧情", "故事", "关系", "经历", "事件", "日历"),
    "general_game": ("1999是什么游戏", "重返未来是什么", "Reverse: 1999", "游戏介绍", "玩法"),
    "meta_question": ("你是谁", "怎么使用", "如何使用", "能做什么"),
    # Legacy aliases kept while old callers/tests still use these names.
    "profile": ("介绍", "是谁", "基础", "生日", "属性", "星级", "定位"),
    "lore": ("剧情", "故事", "关系", "经历", "事件", "日历"),
}
QUERY_KEYWORDS = INTENT_QUERY_KEYWORDS


@dataclass(frozen=True)
class SectionGroup:
    source: str
    heading_path: str
    items: tuple[RetrievalCandidate, ...]
    score: float
    debug: dict[str, float | str]


class RobustIntentRouter:
    """Combine Stage 0 intent with actual Stage 1 headings before packing context."""

    def rerank(self, plan: QueryPlan, candidates: list[RetrievalCandidate], limit: int) -> list[dict]:
        if not candidates:
            return []
        router_intent = self._confirm_intent(plan, candidates)
        groups = self._group(candidates)
        scored = [self._score_group(plan, router_intent, group) for group in groups]
        scored.sort(key=lambda group: (-group.score, group.source, min(item.chunk_index for item in group.items)))
        return self._pack(plan, router_intent, scored, limit)

    def _confirm_intent(self, plan: QueryPlan, candidates: list[RetrievalCandidate]) -> str:
        if plan.intent != "general":
            return plan.intent
        headings = " ".join(item.heading_path for item in candidates)
        query = plan.normalized_query + " " + plan.original_query
        for intent, hints in INTENT_SECTION_HINTS.items():
            if any(hint and hint in headings for hint in hints):
                if any(keyword in query for keyword in INTENT_QUERY_KEYWORDS.get(intent, ())):
                    return intent
        if any(keyword in query for keyword in INTENT_QUERY_KEYWORDS["skill"]):
            return "skill"
        return "general"

    def _group(self, candidates: list[RetrievalCandidate]) -> list[SectionGroup]:
        buckets: dict[tuple[str, str], list[RetrievalCandidate]] = defaultdict(list)
        for item in candidates:
            buckets[(item.source, item.heading_path)].append(item)
        groups: list[SectionGroup] = []
        for (source, heading_path), items in buckets.items():
            ordered = tuple(sorted(items, key=lambda item: item.chunk_index))
            groups.append(SectionGroup(source=source, heading_path=heading_path, items=ordered, score=0.0, debug={}))
        return groups

    def _score_group(self, plan: QueryPlan, router_intent: str, group: SectionGroup) -> SectionGroup:
        hints = plan.section_hints or INTENT_SECTION_HINTS.get(router_intent, ())
        heading = group.heading_path
        content = "\n".join(item.content for item in group.items)
        section_score = 40.0 if any(hint and hint in heading for hint in hints) else 0.0
        keyword_score = self._keyword_score(plan, router_intent, heading + "\n" + content)
        vector_score = max((item.vector_score for item in group.items), default=0.0) * 20.0
        entity_score = 10.0 if plan.entity and any(item.name == plan.entity for item in group.items) else 0.0
        adjacency_bonus = 5.0 if len(group.items) > 1 else 0.0
        noise_penalty = self._noise_penalty(router_intent, heading)
        score = section_score + keyword_score + vector_score + entity_score + adjacency_bonus - noise_penalty
        return SectionGroup(
            source=group.source,
            heading_path=group.heading_path,
            items=group.items,
            score=score,
            debug={
                "router_intent": router_intent,
                "section_score": section_score,
                "keyword_score": keyword_score,
                "vector_score": vector_score,
                "entity_score": entity_score,
                "adjacency_bonus": adjacency_bonus,
                "noise_penalty": noise_penalty,
            },
        )

    def _keyword_score(self, plan: QueryPlan, router_intent: str, text: str) -> float:
        keywords = INTENT_QUERY_KEYWORDS.get(router_intent, ())
        query_text = plan.normalized_query + " " + plan.original_query
        score = 0.0
        for keyword in keywords:
            if keyword in query_text and keyword in text:
                score += 6.0
        return min(score, 24.0)

    def _noise_penalty(self, router_intent: str, heading_path: str) -> float:
        if router_intent == "voice":
            return 0.0
        if "语音" in heading_path:
            return 28.0
        if router_intent == "item" and "单品" in heading_path:
            return 0.0
        if router_intent in {"story", "lore"} and "箱中日历" in heading_path:
            return 0.0
        if router_intent in {"lore", "story", "general"}:
            return 0.0
        return 8.0 if any(noise in heading_path for noise in NOISE_HEADINGS) else 0.0

    def _pack(self, plan: QueryPlan, router_intent: str, groups: list[SectionGroup], limit: int) -> list[dict]:
        packed: list[dict] = []
        for group in groups:
            for item in group.items:
                packed.append({
                    "name": item.name,
                    "category": item.category,
                    "source": item.source,
                    "score": float(group.score),
                    "content": item.content,
                    "heading_path": item.heading_path,
                    "chunk_index": item.chunk_index,
                    "retrieval_stage": item.retrieval_stage,
                    "debug": {
                        **group.debug,
                        "intent": plan.intent,
                        "router_intent": router_intent,
                    },
                })
                if len(packed) >= limit:
                    return packed
        return packed
