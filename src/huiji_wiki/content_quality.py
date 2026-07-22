"""Read-only quality inspection for generated Wiki content blocks."""
from __future__ import annotations

from collections.abc import Mapping, Sequence


def build_content_quality_report(pages: Sequence[Mapping[str, object]]) -> dict[str, object]:
    issues: list[dict[str, object]] = []
    for page in pages:
        content = page.get("content_json")
        content = content if isinstance(content, Mapping) else {}
        blocks = content.get("blocks")
        blocks = blocks if isinstance(blocks, list) else []
        page_id = str(page.get("page_id") or "")
        is_crawler_character = page_id.startswith("char:") and bool(content.get("crawlerProjectionVersion"))
        flags: list[str] = []
        if not blocks:
            flags.append("empty_blocks")
        if str(content.get("summary") or "").strip() == str(page.get("title") or "").strip():
            flags.append("title_only_summary")
        if len(blocks) > 120 and not is_crawler_character:
            flags.append("excessive_block_count")
        if any(isinstance(block, Mapping) and block.get("type") == "paragraph" and len(str(block.get("text") or "")) > 240 for block in blocks):
            flags.append("oversized_paragraph")
        if flags:
            issues.append({"pageId": str(page.get("page_id") or ""), "route": str(page.get("route") or ""), "flags": flags})
    return {
        "schemaVersion": "wiki.content-quality/v1",
        "pageCount": len(pages),
        "issuePageCount": len(issues),
        "issues": issues,
    }
