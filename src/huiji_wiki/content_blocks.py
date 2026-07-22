"""Deterministic structured Wiki content block construction."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any


_FACT = re.compile(r"^\s*([^:：\n]{1,40})\s*[:：]\s*(.*?)\s*$")


def _id(page_id: str, child_id: str, index: int, kind: str) -> str:
    return "block:" + hashlib.sha1(f"{page_id}|{child_id}|{index}|{kind}".encode("utf-8")).hexdigest()[:16]


def _block(page_id: str, child: Mapping[str, object], index: int, kind: str, **values: Any) -> dict[str, object]:
    return {
        "id": _id(page_id, str(child.get("child_id") or ""), index, kind),
        "type": kind,
        "section": str(child.get("section_kind") or "content"),
        "mediaIds": [str(item) for item in (child.get("media_ids") or []) if item],
        **values,
    }


def _normal(value: object) -> str:
    return unicodedata.normalize("NFC", str(value or "").replace("\r\n", "\n").replace("\r", "\n")).strip()


def build_content_blocks(page_id: str, children: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    block_index = 0
    for child in children:
        section = str(child.get("section_kind") or "")
        text = _normal(child.get("text") or child.get("search_text"))
        if not text and not child.get("media_ids"):
            continue
        if section == "voice":
            result.append(_block(page_id, child, block_index, "voice_reference", title=_normal(child.get("title")), text=text))
            block_index += 1
            continue

        specialized = _specialized_blocks(page_id, child, block_index, section, text)
        if specialized:
            result.extend(specialized)
            block_index += len(specialized)
            continue

        chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n", text) if chunk.strip()]
        for chunk in chunks:
            lines = chunk.splitlines()
            heading_lines = [line for line in lines if re.match(r"^#{1,6}\s+", line)]
            for line in heading_lines:
                level = len(line) - len(line.lstrip("#"))
                result.append(_block(page_id, child, block_index, "heading", level=level, text=line[level:].strip()))
                block_index += 1
            lines = [line for line in lines if line not in heading_lines]
            if not lines:
                continue
            facts = []
            for line in lines:
                match = _FACT.match(line)
                if match and match.group(2) != "":
                    facts.append({"label": match.group(1).strip(), "value": match.group(2).strip()})
            if facts and len(facts) == len(lines):
                result.append(_block(page_id, child, block_index, "facts", items=facts))
            elif all(re.match(r"^\s*[-*+]\s+", line) for line in lines):
                result.append(_block(page_id, child, block_index, "list", items=[re.sub(r"^\s*[-*+]\s+", "", line) for line in lines]))
            elif all(line.lstrip().startswith(">") for line in lines):
                result.append(_block(page_id, child, block_index, "quote", text="\n".join(line.lstrip()[1:].strip() for line in lines)))
            elif len(lines) >= 2 and all("|" in line for line in lines):
                rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines if not re.match(r"^\s*\|?\s*:?-+", line)]
                result.append(_block(page_id, child, block_index, "table", rows=rows))
            else:
                parsed = None
                if chunk[:1] in "[{":
                    try:
                        parsed = json.loads(chunk)
                    except json.JSONDecodeError:
                        pass
                if isinstance(parsed, (dict, list)):
                    if parsed:
                        result.append(_block(page_id, child, block_index, "structured", value=parsed, collapsed=_depth(parsed) > 3))
                    else:
                        continue
                else:
                    for paragraph in _split_long(chunk, 240):
                        result.append(_block(page_id, child, block_index, "paragraph", text=paragraph, reveal=len(paragraph) <= 180))
                        block_index += 1
                    continue
            block_index += 1
    return result


def _specialized_blocks(page_id: str, child: Mapping[str, object], index: int, section: str, text: str) -> list[dict[str, object]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if section == "profile" and len(lines) > 1:
        facts = []
        for line in lines[1:]:
            match = _FACT.match(line)
            if not match or not match.group(2):
                return []
            facts.append({"label": match.group(1).strip(), "value": match.group(2).strip()})
        return [
            _block(page_id, child, index, "heading", level=2, text=lines[0]),
            _block(page_id, child, index + 1, "facts", items=facts),
        ]
    if section == "skill" and len(lines) > 1:
        rows = []
        for line in lines[1:]:
            match = re.match(r"^星级\s*(\d+)\s*/\s*Rank\s*\d+\s*[:：]\s*(.*)$", line, re.IGNORECASE)
            if not match:
                return []
            rows.append([match.group(1), match.group(2).strip()])
        return [
            _block(page_id, child, index, "heading", level=3, text=lines[0]),
            _block(page_id, child, index + 1, "table", rows=[["星级", "效果"], *rows]),
        ]
    return []


def _split_long(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts = re.split(r"(?<=[。！？.!?])", text)
    output: list[str] = []
    current = ""
    for part in parts:
        if current and len(current) + len(part) > limit:
            output.append(current.strip())
            current = ""
        current += part
    if current.strip():
        output.append(current.strip())
    bounded: list[str] = []
    for part in output or [text]:
        bounded.extend(part[index:index + limit] for index in range(0, len(part), limit))
    return bounded


def _depth(value: object) -> int:
    if isinstance(value, dict):
        return 1 + max((_depth(item) for item in value.values()), default=0)
    if isinstance(value, list):
        return 1 + max((_depth(item) for item in value), default=0)
    return 0
