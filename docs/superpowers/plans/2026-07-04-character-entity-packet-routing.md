# Character Entity Packet Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a stable character entity-package RAG path for Huiji crawler data, so broad character questions return a balanced entity package, specific questions return the right section, and omitted sections/media are exposed as explicit follow-up actions.

**Architecture:** The pipeline is split into corpus normalization, v3 indexing, multi-route query planning, hybrid retrieval, layered expansion, response assembly, and frontend rendering. Retrieval ranks child blocks first with structured exact, BM25, dense embedding, and optional reranker, then expands to ancestor and bounded sibling content before budget pruning. Media is attached from the final retained blocks only, with image auto-attach and dedicated voice/video panels for explicit media intents.

**Tech Stack:** Python, FastAPI, Pydantic, Milvus, SiliconFlow `BAAI/bge-m3`, optional SiliconFlow `BAAI/bge-reranker-v2-m3`, local BM25 JSON indexes, React, TypeScript, Zustand, Vitest.

---

## Execution Notes

- Work in `D:\PycharmProjects\nlp\LangChain\1999Search`.
- The user requested no git management for this project, so this plan contains checkpoints instead of git commit steps.
- Rebuilding the Milvus collection and running vectorization are separate operational steps. Code changes prepare `text_child_bge_m3_v3`; the user can run the final build commands after review.
- Do not route current QA through Obsidian data. Obsidian interfaces can remain available, but this plan only indexes and retrieves Huiji crawler output.

## File Structure

### Corpus And Models

- Modify `D:\PycharmProjects\nlp\LangChain\1999Search\src\huiji_rag\models.py`  
  Add hierarchy fields, quality flags, omitted-action labels, and panel metadata to `ParentBlock`, `ChildBlock`, and `MediaAsset`.
- Modify `D:\PycharmProjects\nlp\LangChain\1999Search\src\huiji_rag\io.py`  
  Add `excluded_entities.jsonl` and optional report paths to `HuijiBuildPaths`.
- Create `D:\PycharmProjects\nlp\LangChain\1999Search\src\huiji_rag\text.py`  
  Centralize Huiji text cleanup, HTML stripping, whitespace normalization, and safe short summaries.
- Modify `D:\PycharmProjects\nlp\LangChain\1999Search\src\huiji_rag\normalizer.py`  
  Rebuild character normalization around entity package, parent sections, and child topics.
- Modify `D:\PycharmProjects\nlp\LangChain\1999Search\src\huiji_rag\builder.py`  
  Write excluded entities, quality flags, BM25 inputs, and build manifest counts.
- Modify `D:\PycharmProjects\nlp\LangChain\1999Search\src\huiji_rag\media.py`  
  Attach media by parent/child semantics and produce panel metadata for voice/video.

### Indexing And Retrieval

- Modify `D:\PycharmProjects\nlp\LangChain\1999Search\config\config.py`  
  Add route, reranker, and retrieval budget config dataclasses.
- Modify `D:\PycharmProjects\nlp\LangChain\1999Search\config\settings.yaml`  
  Add default-off reranker and v3 collection settings with empty API-key fields.
- Modify `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\vectorstore.py`  
  Create v3 Milvus schema and map new child fields into documents.
- Modify `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\query_plan.py`  
  Replace single normalized query with `dense_query`, `sparse_query`, `media_query`, `route`, `packet_policy`, `entity_type`, and `secondary_intents`.
- Create `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\packet_policy.py`  
  Register per-entity/per-intent section strategies.
- Create `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\layered_expansion.py`  
  Implement ancestor expansion, bounded sibling expansion, omitted actions, and budget pruning.
- Modify `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\hybrid.py`  
  Keep weighted RRF, add quality/entity/intent rules, and expose explainable ranking details.
- Modify `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\reranker.py`  
  Keep existing robust router tests passing and add optional BGE reranker client behind config.
- Modify `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\retriever.py`  
  Orchestrate multi-signal retrieval, optional reranking, expansion, and response candidate packing.
- Modify `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\chain.py`  
  Return route metadata, omitted actions, media panels, and failure actions.

### Backend And Frontend

- Modify `D:\PycharmProjects\nlp\LangChain\1999Search\backend\schemas.py`  
  Add request route options and response action/panel models.
- Modify `D:\PycharmProjects\nlp\LangChain\1999Search\backend\main.py`  
  Pass route options from REST and SSE.
- Modify `D:\PycharmProjects\nlp\LangChain\1999Search\backend\sse.py`  
  Emit `route`, `omitted_actions`, `failure_actions`, and media panel payloads.
- Modify `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\types\index.ts`  
  Mirror backend request and response types.
- Modify `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\api\sse.ts`  
  Send route options and parse new SSE fields.
- Modify `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\store\chatStore.ts`  
  Store persistent mode switches, temporary rescue actions, and omitted action buttons.
- Modify `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\components\chat\ChatInput.tsx`  
  Render bottom input buttons with independent states and distinct rescue button style.
- Modify `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\components\chat\MessageBubble.tsx`  
  Decouple bubble shell, content, media, and actions to preserve later animation hooks.
- Modify `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\components\chat\MessageAssets.tsx`  
  Route image, voice, and video media into specialized renderers.
- Create `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\components\chat\VoicePanel.tsx`  
  Render short scrollable voice panel with background progress.
- Create `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\components\chat\VideoPanel.tsx`  
  Render one primary video and collapsible related videos.
- Create `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\components\chat\MessageActions.tsx`  
  Render omitted section buttons and temporary rescue buttons as explicit actions.

---

### Task 1: Extend Huiji Data Models And Build Paths

**Files:**
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\huiji_rag\models.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\huiji_rag\io.py`
- Test: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_huiji_rag_models.py`

- [ ] **Step 1: Add failing tests for v3 hierarchy fields**

Add these tests:

```python
from src.huiji_rag.io import build_paths
from src.huiji_rag.models import ChildBlock, MediaAsset, ParentBlock


def test_child_block_v3_fields_round_trip():
    child = ChildBlock(
        child_id="char:3023/skill:302301",
        parent_id="char:3023/skills",
        entity_id="3023",
        entity_name="十四行诗",
        category="character",
        section_kind="skill",
        title="规章之外的咏叹诗",
        text="一星：造成精神创伤。",
        search_text="十四行诗 Sonetto 技能 规章之外的咏叹诗",
        chunk_index=0,
        media_ids=("media:sha1:abc",),
        media_policy="auto",
        source_refs=({"kind": "data_page", "title": "Data:Char/3023.json"},),
        content_hash="hash",
        entity_type="character",
        depth_level=3,
        ancestor_ids=("char:3023", "char:3023/skills"),
        quality_flags=("short_text",),
        route_tags=("skill",),
        omitted_action_label="全部技能",
    )
    row = child.to_json()
    assert row["entity_type"] == "character"
    assert row["depth_level"] == 3
    assert row["ancestor_ids"] == ("char:3023", "char:3023/skills")
    assert ChildBlock.from_json(row).route_tags == ("skill",)


def test_parent_block_v3_fields_round_trip():
    parent = ParentBlock(
        parent_id="char:3023/skills",
        entity_id="3023",
        entity_name="十四行诗",
        entity_aliases=("Sonetto",),
        category="character",
        section_kind="skills",
        title="十四行诗 / 技能",
        summary_text="技能概览",
        source_refs=({"kind": "data_page", "title": "Data:Char/3023.json"},),
        child_ids=("char:3023/skill:302301",),
        content_hash="hash",
        entity_type="character",
        depth_level=1,
        ancestor_ids=("char:3023",),
        quality_flags=(),
        omitted_action_label="全部技能",
    )
    assert ParentBlock.from_json(parent.to_json()).omitted_action_label == "全部技能"


def test_media_asset_panel_fields_round_trip():
    asset = MediaAsset(
        media_id="media:sha1:abc",
        sha1="abc",
        entity_id="3023",
        entity_name="十四行诗",
        parent_id="char:3023/voice",
        child_id="char:3023/voice:default:greeting",
        asset_type="voice",
        mime="audio/ogg",
        filename="voice.ogg",
        title="初遇",
        source_url="https://example.invalid/voice.ogg",
        local_relpath="assets/files/ab/voice.ogg",
        object_key="reverse1999/voice/ab/abc.ogg",
        url="http://127.0.0.1:9002/reverse1999-assets/reverse1999/voice/ab/abc.ogg",
        is_available=True,
        is_common=False,
        attach_policy="on_intent",
        search_text="十四行诗 语音 初遇",
        content_hash="hash",
        panel_group="default",
        sort_order=10,
        duration_ms=0,
        quality_flags=(),
    )
    assert MediaAsset.from_json(asset.to_json()).panel_group == "default"


def test_build_paths_include_excluded_entities(tmp_path):
    class Huiji:
        raw_root = tmp_path / "raw"
        processed_root = tmp_path / "processed"
        build_version = "unit"

    class Cfg:
        huiji = Huiji()

    paths = build_paths(Cfg())
    assert paths.excluded_entities.name == "excluded_entities.jsonl"
    assert paths.build_report.name == "build_report.json"
```

- [ ] **Step 2: Run model tests and confirm they fail**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_huiji_rag_models.py -q
```

Expected: failures mention unexpected keyword arguments such as `entity_type`, `depth_level`, or missing path attributes.

- [ ] **Step 3: Add v3 fields to dataclasses**

Add fields at the end of existing dataclasses so existing constructor calls remain valid:

```python
# ParentBlock additions
entity_type: str = "character"
depth_level: int = 1
ancestor_ids: tuple[str, ...] = ()
quality_flags: tuple[str, ...] = ()
omitted_action_label: str = ""

# ChildBlock additions
entity_type: str = "character"
depth_level: int = 3
ancestor_ids: tuple[str, ...] = ()
quality_flags: tuple[str, ...] = ()
route_tags: tuple[str, ...] = ()
omitted_action_label: str = ""

# MediaAsset additions
panel_group: str = ""
sort_order: int = 0
duration_ms: int = 0
quality_flags: tuple[str, ...] = ()
```

Update every `from_json()` method to read those fields with safe defaults using `_tuple_of_str()` for tuple fields.

- [ ] **Step 4: Add v3 build paths**

Extend `HuijiBuildPaths`:

```python
excluded_entities: Path
build_report: Path
```

Return:

```python
excluded_entities=build_root / "excluded_entities.jsonl",
build_report=build_root / "build_report.json",
```

- [ ] **Step 5: Verify model tests pass**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_huiji_rag_models.py -q
```

Expected: all tests in `test_huiji_rag_models.py` pass.

---

### Task 2: Add Huiji Text Cleanup And Character Normalization Tests

**Files:**
- Create: `D:\PycharmProjects\nlp\LangChain\1999Search\src\huiji_rag\text.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\huiji_rag\normalizer.py`
- Test: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_text_cleaner.py`
- Test: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_huiji_rag_normalizer.py`

- [ ] **Step 1: Add failing text cleanup tests**

Add:

```python
from src.huiji_rag.text import clean_huiji_text, compact_lines, short_summary


def test_clean_huiji_text_removes_html_and_keeps_display_text():
    raw = "<span class='x'>十四行诗</span><br/>基金会成员&nbsp;[[Sonetto]]"
    assert clean_huiji_text(raw) == "十四行诗\n基金会成员 Sonetto"


def test_compact_lines_removes_empty_lines_without_merging_bullets():
    raw = "身份：基金会成员\n\n\n- 技能：规章之外的咏叹诗\n\n"
    assert compact_lines(raw) == "身份：基金会成员\n- 技能：规章之外的咏叹诗"


def test_short_summary_preserves_sentence_boundary():
    text = "第一句。第二句。第三句。"
    assert short_summary(text, max_chars=5) == "第一句。"
```

- [ ] **Step 2: Add failing character entity-package test**

In `test_huiji_rag_normalizer.py`, add a focused payload:

```python
import json

from src.huiji_rag.normalizer import normalize_char_page


def test_normalize_char_page_builds_entity_package_sections():
    row = {
        "title": "Data:Char/3023.json",
        "revid": 1,
        "content_sha256": "sha",
        "content": json.dumps(
            {
                "id": 3023,
                "name": "十四行诗",
                "rare": 4,
                "career": 1,
                "dmgType": 1,
                "skill": {
                    "3023011": {
                        "id": 3023011,
                        "name": "规章之外的咏叹诗",
                        "skillRank": 1,
                        "icon": 302301,
                        "desc_art": "星辰各司其职。",
                        "eff_desc": "单体攻击，造成精神创伤。",
                    },
                    "3023012": {
                        "id": 3023012,
                        "name": "规章之外的咏叹诗",
                        "skillRank": 2,
                        "icon": 302301,
                        "desc_art": "世间完满如初。",
                        "eff_desc": "单体攻击，造成更高精神创伤。",
                    },
                },
                "character_data": [
                    {"type": 1, "title": "身份", "content": "基金会成员，司辰助手。"},
                    {"type": 2, "title": "文化", "content": "她重视秩序与诗歌。"},
                    {"type": 3, "title": "单品", "name": "菱格发带", "desc": "整洁的发带。"},
                ],
            },
            ensure_ascii=False,
        ),
    }
    parents, children = normalize_char_page(row, aliases=("Sonetto",))
    parent_ids = {p.parent_id for p in parents}
    child_ids = {c.child_id for c in children}
    assert "char:3023" in parent_ids
    assert "char:3023/profile" in parent_ids
    assert "char:3023/culture" in parent_ids
    assert "char:3023/items" in parent_ids
    assert "char:3023/skills" in parent_ids
    assert "char:3023/skill:302301" in child_ids
    skill = next(c for c in children if c.child_id == "char:3023/skill:302301")
    assert "一星" in skill.text
    assert "二星" in skill.text
    assert skill.media_policy == "auto"
    assert skill.ancestor_ids == ("char:3023", "char:3023/skills")
```

- [ ] **Step 3: Run cleanup and normalizer tests and confirm they fail**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_text_cleaner.py tests\test_huiji_rag_normalizer.py -q
```

Expected: failures mention missing `src.huiji_rag.text` or missing entity package/section IDs.

- [ ] **Step 4: Implement `src.huiji_rag.text`**

Create these functions:

```python
from __future__ import annotations

import html
import re


def clean_huiji_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\[\[([^|\]]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return compact_lines(text)


def compact_lines(value: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in value.splitlines()]
    return "\n".join(line for line in lines if line)


def short_summary(value: str, max_chars: int = 240) -> str:
    text = compact_lines(value)
    if len(text) <= max_chars:
        return text
    match = re.search(r"[。！？.!?]", text[: max_chars + 20])
    if match:
        return text[: match.end()]
    return text[:max_chars].rstrip()
```

- [ ] **Step 5: Rebuild character normalizer around entity package sections**

Update `normalize_char_page()` so one character produces:

```text
char:{id}
char:{id}/profile
char:{id}/dossier
char:{id}/culture
char:{id}/skills
char:{id}/items
char:{id}/voice
char:{id}/skins
char:{id}/media
```

Use these stable section rules:

```python
SECTION_ORDER = {
    "profile": 10,
    "dossier": 20,
    "culture": 30,
    "skills": 40,
    "items": 50,
    "skins": 60,
    "media": 70,
    "voice": 80,
}

CHARACTER_DATA_TYPE_TO_SECTION = {
    "1": "dossier",
    "2": "culture",
    "3": "items",
}
```

Keep skill star variants grouped by icon/name into one child, and format variants as:

```text
规章之外的咏叹诗
一星：...
二星：...
三星：...
```

- [ ] **Step 6: Verify cleanup and normalizer tests pass**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_text_cleaner.py tests\test_huiji_rag_normalizer.py -q
```

Expected: the new tests pass and existing normalizer tests still pass.

---

### Task 3: Add Excluded Entity Logging And Quality Flags

**Files:**
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\huiji_rag\builder.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\huiji_rag\normalizer.py`
- Test: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_huiji_rag_builder.py`

- [ ] **Step 1: Add failing builder test for placeholder exclusion**

Add:

```python
import json

from src.huiji_rag.builder import should_exclude_entity


def test_should_exclude_placeholder_entity_name():
    row = {"title": "Data:Char/9996.json"}
    payload = {"id": 9996, "name": "???"}
    excluded = should_exclude_entity(row, payload)
    assert excluded == {
        "entity_id": "9996",
        "entity_name": "???",
        "reason": "placeholder_name",
        "source": "Data:Char/9996.json",
    }


def test_should_not_exclude_valid_character_name():
    assert should_exclude_entity(
        {"title": "Data:Char/3023.json"},
        {"id": 3023, "name": "十四行诗"},
    ) is None
```

- [ ] **Step 2: Add failing build output test**

Use a fake source object or existing fixture pattern in `test_huiji_rag_builder.py` and assert:

```python
assert paths.excluded_entities.exists()
rows = [json.loads(line) for line in paths.excluded_entities.read_text(encoding="utf-8").splitlines()]
assert rows[0]["reason"] == "placeholder_name"
assert rows[0]["entity_name"] == "???"
```

- [ ] **Step 3: Run builder tests and confirm they fail**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_huiji_rag_builder.py -q
```

Expected: failures mention missing `should_exclude_entity()` or missing `excluded_entities`.

- [ ] **Step 4: Implement hard exclusions**

Add to `builder.py`:

```python
def should_exclude_entity(row: dict[str, Any], payload: dict[str, Any]) -> dict[str, str] | None:
    entity_id = str(payload.get("id", "")).strip()
    entity_name = str(payload.get("name", "")).strip()
    source = str(row.get("title", ""))
    if not entity_id:
        return {"entity_id": "", "entity_name": entity_name, "reason": "missing_entity_id", "source": source}
    if not entity_name:
        return {"entity_id": entity_id, "entity_name": "", "reason": "empty_entity_name", "source": source}
    if entity_name in {"???", "？??", "？？？"}:
        return {"entity_id": entity_id, "entity_name": entity_name, "reason": "placeholder_name", "source": source}
    return None
```

In `build_huiji_corpus()`, collect excluded rows, print:

```python
print(
    f"[huiji-corpus] excluded entity: id={excluded['entity_id']} "
    f"name={excluded['entity_name']} reason={excluded['reason']} source={excluded['source']}"
)
```

Write `excluded_entities.jsonl` even when empty.

- [ ] **Step 5: Add soft quality flag helper**

Add a small helper in `normalizer.py` or `builder.py`:

```python
def quality_flags_for_text(text: str, entity_name: str) -> tuple[str, ...]:
    flags: list[str] = []
    stripped = text.strip()
    if len(stripped) < 24:
        flags.append("short_text")
    if "<" in stripped and ">" in stripped:
        flags.append("raw_html_noise")
    if not entity_name or entity_name in {"???", "？??", "？？？"}:
        flags.append("weak_entity_name")
    return tuple(flags)
```

Call it when constructing parent and child blocks.

- [ ] **Step 6: Verify builder tests pass**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_huiji_rag_builder.py -q
```

Expected: builder tests pass and test output includes the exclusion log when the placeholder fixture is used.

---

### Task 4: Rework Media Attachment And Panel Metadata

**Files:**
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\huiji_rag\media.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\huiji_rag\builder.py`
- Test: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_huiji_rag_media.py`

- [ ] **Step 1: Add failing tests for asset type policies**

Add:

```python
from src.huiji_rag.media import attach_policy_for, classify_asset_type, panel_group_for


def test_classify_character_media_types():
    assert classify_asset_type("L2d_static-302301 shisihangshi.png") == "portrait"
    assert classify_asset_type("Skill-302301.png") == "skill"
    assert classify_asset_type("voice_default_greeting.ogg") == "voice"
    assert classify_asset_type("character_pv.mp4") == "video"


def test_voice_and_video_are_on_intent():
    assert attach_policy_for("voice") == "on_intent"
    assert attach_policy_for("video") == "on_intent"
    assert attach_policy_for("portrait") == "auto"


def test_panel_group_for_voice_prefers_skin_or_default():
    assert panel_group_for("voice", "voice_default_greeting.ogg", child_id="char:3023/voice:default:greeting") == "default"
    assert panel_group_for("voice", "voice_skin_302303_idle.ogg", child_id="char:3023/voice:skin:302303:idle") == "skin:302303"
```

- [ ] **Step 2: Run media tests and confirm they fail**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_huiji_rag_media.py -q
```

Expected: failure mentions missing `panel_group_for()` or wrong policy.

- [ ] **Step 3: Implement panel grouping**

Add:

```python
def panel_group_for(asset_type: str, filename: str, child_id: str) -> str:
    lowered = filename.lower()
    if asset_type == "voice":
        if "skin:" in child_id:
            return child_id.split("skin:", 1)[1].split(":", 1)[0].join(("skin:", ""))
        if "skin_" in lowered:
            token = lowered.split("skin_", 1)[1].split("_", 1)[0]
            return f"skin:{token}"
        return "default"
    if asset_type == "video":
        return "video"
    return ""
```

Set `panel_group`, `sort_order`, and `quality_flags` in `resolve_media_assets()`. Sort assets by:

```python
("default" not in panel_group, asset_type, filename)
```

- [ ] **Step 4: Restrict default media attachment to final child media**

In `builder.py`, keep `media_ids` on the child block that owns the media. Do not copy media IDs to unrelated children. In later retrieval tasks, media lookup must filter by final retained `child_id` and `parent_id`.

- [ ] **Step 5: Verify media tests pass**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_huiji_rag_media.py -q
```

Expected: all media tests pass.

---

### Task 5: Add Config For V3 Collection, Route Options, And Optional Reranker

**Files:**
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\config\config.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\config\settings.yaml`
- Test: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_config.py`

- [ ] **Step 1: Add failing config test**

Add:

```python
from config.config import get_config, reset_config_for_test


def test_route_and_reranker_config_defaults(monkeypatch):
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    reset_config_for_test()
    cfg = get_config()
    assert cfg.huiji.text_collection_name == "text_child_bge_m3_v3"
    assert cfg.vectorstore.collection_name == "text_child_bge_m3_v3"
    assert cfg.reranker.enabled is False
    assert cfg.reranker.model == "BAAI/bge-reranker-v2-m3"
    assert cfg.retrieval.bm25_k == 40
    assert cfg.retrieval.dense_k == 40
    assert cfg.retrieval.rerank_k == 60
```

- [ ] **Step 2: Run config test and confirm it fails**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_config.py -q
```

Expected: failure mentions missing `reranker` or `retrieval`.

- [ ] **Step 3: Add config dataclasses**

Add:

```python
@dataclass
class RerankerCfg:
    enabled: bool
    provider: str
    base_url: str
    model: str
    api_key: str


@dataclass
class RetrievalCfg:
    bm25_k: int
    dense_k: int
    rerank_k: int
    context_budget_chars: int
    sibling_window: int
```

Add fields to `Config`:

```python
reranker: RerankerCfg
retrieval: RetrievalCfg
```

Read `SILICONFLOW_API_KEY` for reranker when no separate key is provided.

- [ ] **Step 4: Update settings**

Set v3 collection names and add config blocks:

```yaml
vectorstore:
  provider: "milvus"
  uri: "http://127.0.0.1:19530"
  db_name: "reverse1999_rag"
  collection_name: "text_child_bge_m3_v3"
huiji:
  enabled: true
  raw_root: "data/huiji/res1999"
  processed_root: "data/processed/huiji"
  build_version: "dev"
  text_collection_name: "text_child_bge_m3_v3"
  asset_caption_collection_name: "asset_caption_bge_m3_v1"
reranker:
  enabled: false
  provider: "siliconflow"
  base_url: "https://api.siliconflow.cn/v1"
  model: "BAAI/bge-reranker-v2-m3"
  api_key: ""
retrieval:
  bm25_k: 40
  dense_k: 40
  rerank_k: 60
  context_budget_chars: 9000
  sibling_window: 1
```

- [ ] **Step 5: Verify config test passes**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_config.py -q
```

Expected: config tests pass and no API key is written into `settings.yaml`.

---

### Task 6: Create Milvus V3 Schema And Index Build Mapping

**Files:**
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\vectorstore.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\scripts\build_huiji_index.py`
- Test: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_huiji_vectorstore.py`

- [ ] **Step 1: Add failing v3 row mapping test**

Add:

```python
from src.rag.vectorstore import huiji_child_to_milvus_row, validate_huiji_child_for_milvus


def test_huiji_child_to_milvus_row_v3_fields():
    child = {
        "child_id": "char:3023/skill:302301",
        "parent_id": "char:3023/skills",
        "entity_id": "3023",
        "entity_name": "十四行诗",
        "entity_type": "character",
        "category": "character",
        "section_kind": "skill",
        "title": "规章之外的咏叹诗",
        "text": "一星：造成精神创伤。",
        "search_text": "十四行诗 Sonetto 技能 规章之外的咏叹诗",
        "chunk_index": 0,
        "depth_level": 3,
        "ancestor_ids": ("char:3023", "char:3023/skills"),
        "media_policy": "auto",
        "media_ids": ("media:sha1:abc",),
        "quality_flags": ("short_text",),
        "route_tags": ("skill",),
        "source_refs": ({"kind": "data_page", "title": "Data:Char/3023.json"},),
        "content_hash": "hash",
    }
    validate_huiji_child_for_milvus(child, row_number=1)
    row = huiji_child_to_milvus_row(child, [0.0] * 1024)
    assert row["id"] == "char:3023/skill:302301"
    assert row["entity_type"] == "character"
    assert row["depth_level"] == 3
    assert '"char:3023/skills"' in row["ancestor_ids"]
    assert '"skill"' in row["route_tags"]
```

- [ ] **Step 2: Run vectorstore tests and confirm they fail**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_huiji_vectorstore.py -q
```

Expected: failure mentions missing row fields or validation limits.

- [ ] **Step 3: Extend `HUIJI_VARCHAR_LIMITS` and schema**

Add fields:

```python
"entity_type": 64,
"title": 512,
"ancestor_ids": 2048,
"quality_flags": 1024,
"route_tags": 1024,
```

Add schema fields:

```python
schema.add_field("entity_type", DataType.VARCHAR, max_length=64)
schema.add_field("title", DataType.VARCHAR, max_length=512)
schema.add_field("depth_level", DataType.INT64)
schema.add_field("ancestor_ids", DataType.VARCHAR, max_length=2048)
schema.add_field("quality_flags", DataType.VARCHAR, max_length=1024)
schema.add_field("route_tags", DataType.VARCHAR, max_length=1024)
```

Keep dynamic field enabled so later non-breaking metadata can be stored.

- [ ] **Step 4: Map v3 fields into Milvus rows and documents**

In `huiji_child_to_milvus_row()`, write JSON strings for tuple/list fields. In `milvus_entity_to_document()`, preserve the same fields in metadata.

- [ ] **Step 5: Verify vectorstore tests pass**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_huiji_vectorstore.py -q
```

Expected: v3 mapping tests pass.

---

### Task 7: Upgrade QueryPlan To Multi-Route JSON

**Files:**
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\query_plan.py`
- Test: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_query_plan.py`

- [ ] **Step 1: Add failing tests for multi-route fields**

Add:

```python
from src.rag.query_plan import QueryPlan, QueryPlanner


def test_query_plan_fallback_intro_uses_separate_queries():
    plan = QueryPlanner(None).plan("介绍一下十四行诗")
    assert plan.entity == "十四行诗"
    assert plan.entity_type == "character"
    assert plan.intent == "intro"
    assert plan.packet_policy == "intro_full"
    assert "十四行诗" in plan.dense_query
    assert "十四行诗" in plan.sparse_query
    assert plan.route == "rag_grounded"


def test_query_plan_from_llm_payload_accepts_route_options():
    planner = QueryPlanner(None)
    payload = {
        "normalized_query": "十四行诗技能",
        "entity": "十四行诗",
        "entity_type": "character",
        "intent": "skill",
        "dense_query": "十四行诗的技能效果",
        "sparse_query": "十四行诗 Sonetto 技能",
        "media_query": "十四行诗 技能图",
        "aliases": ["Sonetto"],
        "scatter_terms": ["十四行诗", "Sonetto"],
        "packet_policy": "section_detail",
        "target_levels": ["parent", "child"],
        "secondary_intents": [],
        "route": "expanded_rag",
        "confidence": 0.8,
        "media_intent": "image",
    }
    plan = planner._from_payload("十四行诗的技能是什么", payload)
    assert plan.dense_query == "十四行诗的技能效果"
    assert plan.sparse_query == "十四行诗 Sonetto 技能"
    assert plan.packet_policy == "section_detail"
    assert plan.route == "expanded_rag"
```

- [ ] **Step 2: Run query plan tests and confirm they fail**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_query_plan.py -q
```

Expected: failure mentions missing fields.

- [ ] **Step 3: Replace QueryPlan dataclass fields**

Add these fields while keeping existing ones where callers still use them:

```python
entity_type: str | None = None
dense_query: str = ""
sparse_query: str = ""
media_query: str = ""
packet_policy: str = "default"
target_levels: tuple[str, ...] = ()
secondary_intents: tuple[str, ...] = ()
route: str = "rag_grounded"
route_options: dict[str, bool] | None = None
```

Keep `normalized_query` as compatibility alias and set it to `dense_query or normalized_query or original_query`.

- [ ] **Step 4: Update valid intents and fallback heuristics**

Use:

```python
VALID_INTENTS = {
    "intro", "profile_fact", "skill", "item", "culture", "voice",
    "media", "psychube", "story", "general", "general_game", "meta_question",
}
```

Fallback mapping:

```text
介绍/是谁 -> intro
生日/星级/职业/属性/伤害类型 -> profile_fact
技能/神秘术/大招/终仪/传承/塑造 -> skill
单品/物品/尤提姆 -> item
语音/台词/播放 -> voice
立绘/图片/皮肤/视频/PV -> media
1999是什么游戏 -> general_game
你是谁/怎么用 -> meta_question
```

- [ ] **Step 5: Update system prompt to request strict JSON**

The prompt must ask for exactly these keys:

```json
{
  "normalized_query": "",
  "entity": null,
  "entity_type": null,
  "intent": "general",
  "dense_query": "",
  "sparse_query": "",
  "media_query": "",
  "aliases": [],
  "scatter_terms": [],
  "packet_policy": "default",
  "target_levels": [],
  "secondary_intents": [],
  "route": "rag_grounded",
  "confidence": 0.0,
  "media_intent": "none"
}
```

- [ ] **Step 6: Verify query plan tests pass**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_query_plan.py -q
```

Expected: query plan tests pass.

---

### Task 8: Add Packet Policy Registry

**Files:**
- Create: `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\packet_policy.py`
- Test: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_entity_packet.py`

- [ ] **Step 1: Add failing policy tests**

Add:

```python
from src.rag.packet_policy import get_packet_policy


def test_character_intro_policy_sections():
    policy = get_packet_policy("character", "intro")
    assert policy.name == "intro_full"
    assert policy.sections == ("dossier", "profile", "culture", "skills", "items", "media")
    assert policy.auto_media_types == ("portrait", "image")
    assert policy.omitted_parent_actions is True


def test_character_voice_policy_uses_voice_panel():
    policy = get_packet_policy("character", "voice")
    assert policy.sections == ("voice",)
    assert policy.panel == "voice"
    assert policy.auto_media_types == ()
    assert policy.intent_media_types == ("voice",)
```

- [ ] **Step 2: Run packet policy tests and confirm they fail**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_entity_packet.py -q
```

Expected: failure mentions missing `src.rag.packet_policy`.

- [ ] **Step 3: Implement registry**

Create:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PacketPolicy:
    name: str
    sections: tuple[str, ...]
    output_mode: str
    panel: str = ""
    auto_media_types: tuple[str, ...] = ()
    intent_media_types: tuple[str, ...] = ()
    omitted_parent_actions: bool = False
    context_budget_chars: int = 9000


CHARACTER_POLICIES: dict[str, PacketPolicy] = {
    "intro": PacketPolicy(
        name="intro_full",
        sections=("dossier", "profile", "culture", "skills", "items", "media"),
        output_mode="encyclopedia_summary",
        auto_media_types=("portrait", "image"),
        omitted_parent_actions=True,
    ),
    "profile_fact": PacketPolicy(
        name="profile_fact",
        sections=("profile", "dossier"),
        output_mode="fact_answer",
        auto_media_types=("portrait",),
    ),
    "skill": PacketPolicy(
        name="section_detail",
        sections=("skills",),
        output_mode="section_detail",
        auto_media_types=("skill",),
    ),
    "item": PacketPolicy(
        name="section_detail",
        sections=("items",),
        output_mode="section_detail",
        auto_media_types=("image",),
    ),
    "culture": PacketPolicy(
        name="section_detail",
        sections=("culture", "dossier"),
        output_mode="section_detail",
        auto_media_types=("image",),
    ),
    "media": PacketPolicy(
        name="media_detail",
        sections=("media", "skins", "profile"),
        output_mode="media_detail",
        auto_media_types=("portrait", "image"),
    ),
    "voice": PacketPolicy(
        name="voice_detail",
        sections=("voice",),
        output_mode="panel",
        panel="voice",
        intent_media_types=("voice",),
    ),
    "video": PacketPolicy(
        name="video_detail",
        sections=("media",),
        output_mode="panel",
        panel="video",
        intent_media_types=("video",),
    ),
}


def get_packet_policy(entity_type: str | None, intent: str) -> PacketPolicy:
    if entity_type == "character":
        return CHARACTER_POLICIES.get(intent, CHARACTER_POLICIES["intro"])
    return PacketPolicy(name="default", sections=(), output_mode="rag")
```

- [ ] **Step 4: Verify packet policy tests pass**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_entity_packet.py -q
```

Expected: packet policy tests pass.

---

### Task 9: Implement Layered Expansion And Omitted Actions

**Files:**
- Create: `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\layered_expansion.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\hybrid.py`
- Test: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_hybrid_retriever.py`

- [ ] **Step 1: Add failing layered expansion test**

Add:

```python
from src.rag.layered_expansion import expand_ranked_children
from src.rag.packet_policy import get_packet_policy


def test_intro_expands_parent_sections_and_returns_omitted_actions():
    children = [
        {"child_id": "char:3023/profile:0000", "parent_id": "char:3023/profile", "entity_name": "十四行诗", "section_kind": "profile", "chunk_index": 0, "text": "基础资料", "score": 0.9},
        {"child_id": "char:3023/skill:302301", "parent_id": "char:3023/skills", "entity_name": "十四行诗", "section_kind": "skill", "chunk_index": 0, "text": "技能一", "score": 0.8},
        {"child_id": "char:3023/item:1", "parent_id": "char:3023/items", "entity_name": "十四行诗", "section_kind": "item", "chunk_index": 0, "text": "单品一", "score": 0.4},
    ]
    ranked = [children[1]]
    result = expand_ranked_children(
        ranked=ranked,
        all_children=children,
        policy=get_packet_policy("character", "intro"),
        budget_chars=12,
        sibling_window=1,
    )
    retained_ids = [row["child_id"] for row in result.sources]
    assert "char:3023/profile:0000" in retained_ids
    assert "char:3023/skill:302301" in retained_ids
    assert result.omitted_actions
    assert result.omitted_actions[0]["intent"] in {"item", "skill", "media", "culture", "voice"}
```

- [ ] **Step 2: Run hybrid tests and confirm they fail**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_hybrid_retriever.py -q
```

Expected: failure mentions missing `layered_expansion`.

- [ ] **Step 3: Implement expansion result dataclass**

Create:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExpansionResult:
    sources: list[dict[str, Any]]
    omitted_actions: list[dict[str, Any]]
    debug: dict[str, Any]
```

- [ ] **Step 4: Implement deterministic expansion**

`expand_ranked_children()` must:

1. Build `children_by_parent`.
2. Keep ranked hits for requested policy sections.
3. Add same-entity profile child for `intro`.
4. Add siblings in the same parent within `sibling_window`.
5. Sort by adjusted score and section order.
6. Trim by `budget_chars`.
7. Convert unretained same-entity parents/children into `omitted_actions`.

The omitted action payload shape:

```python
{
    "label": "全部技能",
    "query": "介绍十四行诗的技能",
    "entity": "十四行诗",
    "entity_type": "character",
    "intent": "skill",
    "packet_policy": "section_detail",
    "target_parent_id": "char:3023/skills",
}
```

- [ ] **Step 5: Verify hybrid tests pass**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_hybrid_retriever.py -q
```

Expected: expansion test passes and existing RRF tests still pass.

---

### Task 10: Integrate Optional BGE Reranker Before Expansion

**Files:**
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\reranker.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\retriever.py`
- Test: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_reranker.py`
- Test: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_retriever.py`

- [ ] **Step 1: Add failing reranker disabled test**

Add:

```python
from src.rag.reranker import OptionalBgeReranker


def test_optional_reranker_disabled_returns_input_order():
    reranker = OptionalBgeReranker(enabled=False, base_url="", api_key="", model="BAAI/bge-reranker-v2-m3")
    rows = [{"child_id": "a", "text": "A"}, {"child_id": "b", "text": "B"}]
    assert reranker.rerank("query", rows) == rows
```

- [ ] **Step 2: Add failing reranker enabled mock test**

Add:

```python
class FakeClient:
    def score(self, query, documents):
        assert query == "十四行诗技能"
        return [0.2, 0.9]


def test_optional_reranker_enabled_uses_scores():
    reranker = OptionalBgeReranker(
        enabled=True,
        base_url="https://api.siliconflow.cn/v1",
        api_key="key",
        model="BAAI/bge-reranker-v2-m3",
        client=FakeClient(),
    )
    rows = [{"child_id": "a", "text": "A"}, {"child_id": "b", "text": "B"}]
    ranked = reranker.rerank("十四行诗技能", rows)
    assert [row["child_id"] for row in ranked] == ["b", "a"]
    assert ranked[0]["debug"]["reranker_score"] == 0.9
```

- [ ] **Step 3: Run reranker tests and confirm they fail**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_reranker.py -q
```

Expected: failure mentions missing `OptionalBgeReranker`.

- [ ] **Step 4: Implement optional reranker wrapper**

Add `OptionalBgeReranker` with:

```python
def rerank(self, query: str, rows: list[dict[str, Any]], limit: int | None = None) -> list[dict[str, Any]]:
    if not self.enabled or not rows:
        return rows[:limit] if limit else rows
    documents = [str(row.get("text") or row.get("search_text") or "") for row in rows]
    scores = self.client.score(query, documents)
    scored = []
    for row, score in zip(rows, scores):
        item = dict(row)
        debug = dict(item.get("debug", {}))
        debug["reranker_score"] = float(score)
        item["debug"] = debug
        item["score"] = float(item.get("score", 0.0)) + float(score)
        scored.append(item)
    scored.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
    return scored[:limit] if limit else scored
```

- [ ] **Step 5: Wire reranker before expansion**

In `Retriever.search()`:

```text
BM25 top 40 + dense top 40
-> weighted_rrf merge and dedupe
-> optional rerank max 60
-> layered expansion
-> return final sources
```

Do not rerank expanded parent/sibling rows; rerank child candidates only.

- [ ] **Step 6: Verify reranker and retriever tests pass**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_reranker.py tests\test_retriever.py -q
```

Expected: tests pass with reranker disabled by default.

---

### Task 11: Update Retriever To Use Multi-Signal Fields And Policies

**Files:**
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\retriever.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\hybrid.py`
- Test: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_retriever.py`
- Test: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_hybrid_retriever.py`

- [ ] **Step 1: Add failing sparse/dense query split test**

Add:

```python
def test_retriever_uses_sparse_query_for_bm25_and_dense_query_for_embedding(fake_huiji_retriever):
    plan = fake_huiji_retriever.plan(
        entity="十四行诗",
        intent="skill",
        dense_query="十四行诗的技能效果",
        sparse_query="十四行诗 Sonetto 技能 Skill-302301",
    )
    fake_huiji_retriever.search("ignored", query_plan=plan)
    assert fake_huiji_retriever.sparse_last_query == "十四行诗 Sonetto 技能 Skill-302301"
    assert fake_huiji_retriever.dense_last_query == "十四行诗的技能效果"
```

If existing fixtures do not provide `fake_huiji_retriever`, implement a minimal test double in the test file with methods `search()`, `similarity_search_with_relevance_scores()`, and `LocalBM25SparseIndex.search()`.

- [ ] **Step 2: Add failing anomaly penalty test**

Add:

```python
from src.rag.hybrid import weighted_rrf


def test_weighted_rrf_filters_hard_excluded_and_penalizes_quality_flags():
    rows = [
        {"child_id": "bad", "entity_name": "???", "category": "character", "section_kind": "profile", "quality_flags": ["weak_entity_name"]},
        {"child_id": "good", "entity_name": "十四行诗", "category": "character", "section_kind": "profile", "quality_flags": []},
    ]
    ranked = weighted_rrf(rows, [], entity="十四行诗", intent="intro")
    assert [row["child_id"] for row in ranked] == ["good"]
```

- [ ] **Step 3: Run retriever tests and confirm they fail**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_retriever.py tests\test_hybrid_retriever.py -q
```

Expected: failures mention old normalized query path or anomaly rows not filtered.

- [ ] **Step 4: Update retrieval query selection**

Use:

```python
bm25_query = query_plan.sparse_query or query_plan.normalized_query or query
dense_query = query_plan.dense_query or query_plan.normalized_query or query
policy = get_packet_policy(query_plan.entity_type, query_plan.intent)
```

Set candidate sizes from `cfg.retrieval`.

- [ ] **Step 5: Add structured exact candidates**

Before BM25/dense, add local child rows where:

```text
entity_name == plan.entity
category == "character"
section_kind in policy.sections or policy.sections empty
```

For `intro`, include all same-entity policy sections as candidates with a structured-exact score bonus.

- [ ] **Step 6: Apply hard filter and quality penalties**

Drop rows with:

```python
row.get("entity_name") in {"", "???", "？??", "？？？"}
```

Penalize:

```text
weak_entity_name: -0.50
raw_html_noise: -0.20
short_text: -0.05
missing_media: -0.05
```

Keep penalties in `debug`.

- [ ] **Step 7: Verify retriever tests pass**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_retriever.py tests\test_hybrid_retriever.py -q
```

Expected: tests pass.

---

### Task 12: Return Route Metadata, Failure Actions, Omitted Actions, And Media Panels

**Files:**
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\chain.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\assets\huiji_registry.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\backend\schemas.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\backend\main.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\backend\sse.py`
- Test: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_chain_assets.py`
- Test: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_sse.py`

- [ ] **Step 1: Add failing chain response test**

Add:

```python
def test_chain_retrieve_returns_actions_and_route(fake_chain):
    result = fake_chain.retrieve("介绍一下十四行诗")
    assert "route" in result
    assert "omitted_actions" in result
    assert "failure_actions" in result
    assert "media_panels" in result
```

- [ ] **Step 2: Add failing SSE payload test**

Add to `test_sse.py`:

```python
def test_sources_event_includes_actions_and_route():
    payload = make_sources_event_payload()
    assert payload["route"]["name"] == "rag_grounded"
    assert isinstance(payload["omitted_actions"], list)
    assert isinstance(payload["failure_actions"], list)
```

Use existing SSE test helpers if present; otherwise build the event string with `sse_event()` and parse `data:`.

- [ ] **Step 3: Run chain and SSE tests and confirm they fail**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_chain_assets.py tests\test_sse.py -q
```

Expected: failures mention missing response keys.

- [ ] **Step 4: Add backend models**

Add Pydantic models:

```python
class RouteOptions(BaseModel):
    expanded: bool = False
    free_supplement: bool = False


class ActionItem(BaseModel):
    label: str
    query: str
    entity: str = ""
    entity_type: str = ""
    intent: str = ""
    packet_policy: str = ""
    target_parent_id: Optional[str] = None


class RouteInfo(BaseModel):
    name: str
    confidence: float = 0.0
    intent: str = ""
    entity: Optional[str] = None
```

Extend `AskRequest` with:

```python
route_options: RouteOptions = RouteOptions()
action_payload: Optional[ActionItem] = None
```

Extend `AskResponse` with:

```python
route: Optional[RouteInfo] = None
omitted_actions: list[ActionItem] = []
failure_actions: list[ActionItem] = []
media_panels: list[dict] = []
```

- [ ] **Step 5: Add failure actions**

When no reliable sources are found and route is not `llm_general`, return:

```python
[
    {"label": "扩大范围重新搜索", "query": question, "intent": "expanded_rag", "packet_policy": "expanded"},
    {"label": "使用自由补充重答", "query": question, "intent": "llm_general", "packet_policy": "free_supplement"},
]
```

These actions must not mutate persistent route options.

- [ ] **Step 6: Restrict media to final sources**

In `HuijiMediaRegistry.find_for_retrieval()`, build allowed IDs from final sources:

```python
allowed_child_ids = {source.get("child_id") for source in sources}
allowed_parent_ids = {source.get("parent_id") for source in sources}
```

Only return media where `child_id` or `parent_id` is allowed and `attach_policy` matches the current policy.

- [ ] **Step 7: Verify chain and SSE tests pass**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_chain_assets.py tests\test_sse.py -q
```

Expected: tests pass and SSE event includes route/action/media panel fields.

---

### Task 13: Add Frontend Request Options And Action State

**Files:**
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\types\index.ts`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\api\sse.ts`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\store\chatStore.ts`
- Test: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\api\sse.test.ts`
- Test: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\store\chatStore.test.ts`

- [ ] **Step 1: Add failing frontend type/store tests**

In `chatStore.test.ts`, add:

```typescript
it('keeps expanded and free supplement toggles independent', () => {
  const store = useChatStore.getState()
  store.setRouteOption('expanded', true)
  expect(useChatStore.getState().routeOptions.expanded).toBe(true)
  expect(useChatStore.getState().routeOptions.freeSupplement).toBe(false)
  store.setRouteOption('freeSupplement', true)
  expect(useChatStore.getState().routeOptions.expanded).toBe(true)
  expect(useChatStore.getState().routeOptions.freeSupplement).toBe(true)
})
```

In `sse.test.ts`, add a fetch body assertion:

```typescript
expect(JSON.parse(fetchBody as string)).toMatchObject({
  question: '介绍一下十四行诗',
  route_options: { expanded: true, free_supplement: false },
})
```

- [ ] **Step 2: Run frontend tests and confirm they fail**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm test -- --run src/api/sse.test.ts src/store/chatStore.test.ts
```

Expected: failures mention missing route option state or missing request fields.

- [ ] **Step 3: Add frontend types**

Add:

```typescript
export interface RouteOptions {
  expanded: boolean
  freeSupplement: boolean
}

export interface ActionItem {
  label: string
  query: string
  entity?: string
  entity_type?: string
  intent?: string
  packet_policy?: string
  target_parent_id?: string | null
}

export interface RouteInfo {
  name: string
  confidence?: number
  intent?: string
  entity?: string | null
}
```

Extend `Message`:

```typescript
route?: RouteInfo
omittedActions?: ActionItem[]
failureActions?: ActionItem[]
mediaPanels?: MediaPanel[]
```

- [ ] **Step 4: Update SSE request body**

Change `streamAsk()` signature to accept:

```typescript
routeOptions: RouteOptions
actionPayload?: ActionItem | null
```

Send backend snake-case:

```typescript
body: JSON.stringify({
  question,
  category,
  route_options: {
    expanded: routeOptions.expanded,
    free_supplement: routeOptions.freeSupplement,
  },
  action_payload: actionPayload ?? null,
})
```

- [ ] **Step 5: Update chat store state**

Add:

```typescript
routeOptions: { expanded: false, freeSupplement: false },
setRouteOption: (key, value) => set((s) => ({ routeOptions: { ...s.routeOptions, [key]: value } })),
runAction: (action) => get().send(action.query, action),
```

Temporary action execution passes `action_payload` but does not change `routeOptions`.

- [ ] **Step 6: Verify frontend API/store tests pass**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm test -- --run src/api/sse.test.ts src/store/chatStore.test.ts
```

Expected: tests pass.

---

### Task 14: Implement Input Bottom Buttons And Message Action Buttons

**Files:**
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\components\chat\ChatInput.tsx`
- Create: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\components\chat\MessageActions.tsx`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\components\chat\MessageBubble.tsx`
- Test: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\components\chat\MessageBubble.test.tsx`

- [ ] **Step 1: Add failing UI test for persistent and rescue buttons**

Add:

```typescript
it('renders persistent route toggles under the input', () => {
  render(<ChatInput />)
  expect(screen.getByRole('button', { name: '扩大检索' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '自由补充' })).toBeInTheDocument()
})

it('renders rescue buttons with distinct labels', () => {
  render(<MessageActions actions={[
    { label: '扩大范围重新搜索', query: '介绍一下十四行诗' },
    { label: '使用自由补充重答', query: '介绍一下十四行诗' },
  ]} variant="rescue" onAction={() => undefined} />)
  expect(screen.getByRole('button', { name: '扩大范围重新搜索' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '使用自由补充重答' })).toBeInTheDocument()
})
```

- [ ] **Step 2: Run component test and confirm it fails**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm test -- --run src/components/chat/MessageBubble.test.tsx
```

Expected: failures mention missing buttons or missing `MessageActions`.

- [ ] **Step 3: Render persistent input toggles**

In `ChatInput.tsx`, keep the input and send button, then add a bottom button row inside the input shell:

```tsx
<div className="chat-input-modes" style={{ display: 'flex', gap: 8, marginTop: 8 }}>
  <button type="button" aria-pressed={routeOptions.expanded} onClick={() => setRouteOption('expanded', !routeOptions.expanded)}>
    扩大检索
  </button>
  <button type="button" aria-pressed={routeOptions.freeSupplement} onClick={() => setRouteOption('freeSupplement', !routeOptions.freeSupplement)}>
    自由补充
  </button>
</div>
```

Use color/fill state for on/off. Do not rename the buttons when toggled.

- [ ] **Step 4: Implement `MessageActions`**

Component props:

```typescript
interface MessageActionsProps {
  actions: ActionItem[]
  variant: 'omitted' | 'rescue'
  onAction: (action: ActionItem) => void
}
```

Style `variant="rescue"` as shorter rounded rectangles. Style omitted actions as compact section buttons.

- [ ] **Step 5: Wire actions into `MessageBubble`**

Render:

```tsx
{!message.streaming && message.omittedActions?.length ? (
  <MessageActions actions={message.omittedActions} variant="omitted" onAction={runAction} />
) : null}
{!message.streaming && message.failureActions?.length ? (
  <MessageActions actions={message.failureActions} variant="rescue" onAction={runAction} />
) : null}
```

- [ ] **Step 6: Verify component tests pass**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm test -- --run src/components/chat/MessageBubble.test.tsx
```

Expected: UI tests pass.

---

### Task 15: Implement Voice And Video Panels

**Files:**
- Create: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\components\chat\VoicePanel.tsx`
- Create: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\components\chat\VideoPanel.tsx`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\components\chat\MessageAssets.tsx`
- Test: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\components\chat\MessageBubble.test.tsx`

- [ ] **Step 1: Add failing panel tests**

Add:

```typescript
it('renders voice panel rows as buttons', () => {
  render(<VoicePanel items={[
    { media_id: 'v1', asset_type: 'voice', mime: 'audio/ogg', url: '/voice.ogg', title: '初遇', panel_group: 'default' },
  ]} />)
  expect(screen.getByRole('button', { name: '初遇' })).toBeInTheDocument()
})

it('renders video panel with one primary video', () => {
  render(<VideoPanel items={[
    { media_id: 'm1', asset_type: 'video', mime: 'video/mp4', url: '/a.mp4', title: '角色PV' },
    { media_id: 'm2', asset_type: 'video', mime: 'video/mp4', url: '/b.mp4', title: '演示' },
  ]} />)
  expect(screen.getByTitle('角色PV')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /更多视频/ })).toBeInTheDocument()
})
```

- [ ] **Step 2: Run panel tests and confirm they fail**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm test -- --run src/components/chat/MessageBubble.test.tsx
```

Expected: failures mention missing panel components.

- [ ] **Step 3: Implement `VoicePanel`**

Rules:

- Max height equivalent to 2-3 text lines with internal scroll.
- Each row is a button.
- On click, play the row audio.
- Playback progress is a background layer, not text color.
- Keep `data-animation-slot="voice-line"` and `data-progress-layer="true"` attributes for future visual effects.

- [ ] **Step 4: Implement `VideoPanel`**

Rules:

- No autoplay.
- Render first video as primary `<video controls preload="metadata">`.
- Render title/source text above or below video.
- Render additional videos inside a collapsed `<details>`.

- [ ] **Step 5: Route media kinds in `MessageAssets`**

Before image grid rendering:

```typescript
const voiceItems = assets.filter((asset) => mediaKind(asset) === 'audio')
const videoItems = assets.filter((asset) => mediaKind(asset) === 'video')
const imageItems = assets.filter((asset) => mediaKind(asset) === 'image')
```

Render `VoicePanel` and `VideoPanel` separately; render images in the existing grid.

- [ ] **Step 6: Verify panel tests pass**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm test -- --run src/components/chat/MessageBubble.test.tsx
```

Expected: panel tests pass.

---

### Task 16: Build Corpus, Rebuild Index, And Verify End-To-End

**Files:**
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\scripts\build_huiji_corpus.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\scripts\build_huiji_index.py`
- Test: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_huiji_pipeline.py`
- Test: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_huiji_eval.py`

- [ ] **Step 1: Add failing pipeline assertions**

Add assertions that the built corpus contains:

```python
assert manifest["parent_count"] > 0
assert manifest["child_count"] > 0
assert "excluded_count" in manifest
assert paths.excluded_entities.exists()
```

Add evaluation cases:

```python
cases = [
    ("介绍一下十四行诗", "十四行诗", "intro"),
    ("十四行诗的技能是什么", "十四行诗", "skill"),
    ("播放十四行诗语音", "十四行诗", "voice"),
    ("十四行诗有没有视频", "十四行诗", "media"),
]
```

Each case must assert the final sources include the target entity unless route is `llm_general`.

- [ ] **Step 2: Run backend test suite subset and confirm failures are limited to planned changes**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_huiji_pipeline.py tests\test_huiji_eval.py -q
```

Expected: failures point to missing manifest fields, missing v3 fields, or old retrieval route behavior.

- [ ] **Step 3: Update corpus script progress output**

Ensure `scripts\build_huiji_corpus.py` prints:

```text
[huiji-corpus] raw_root=...
[huiji-corpus] build_root=...
[huiji-corpus] parents=...
[huiji-corpus] children=...
[huiji-corpus] media=...
[huiji-corpus] excluded=...
```

- [ ] **Step 4: Update index script collection naming**

Ensure `scripts\build_huiji_index.py` defaults to:

```python
collection_name = cfg.huiji.text_collection_name or cfg.vectorstore.collection_name
```

The script should print:

```text
[huiji-index] collection=reverse1999_rag.text_child_bge_m3_v3
[huiji-index] inserted X/Y
[huiji-index] done: reverse1999_rag.text_child_bge_m3_v3
```

- [ ] **Step 5: Verify corpus and evaluation tests pass**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_huiji_pipeline.py tests\test_huiji_eval.py -q
```

Expected: tests pass.

- [ ] **Step 6: Run backend focused tests**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest ^
  tests\test_huiji_rag_models.py ^
  tests\test_text_cleaner.py ^
  tests\test_huiji_rag_normalizer.py ^
  tests\test_huiji_rag_media.py ^
  tests\test_huiji_rag_builder.py ^
  tests\test_huiji_vectorstore.py ^
  tests\test_query_plan.py ^
  tests\test_entity_packet.py ^
  tests\test_hybrid_retriever.py ^
  tests\test_reranker.py ^
  tests\test_retriever.py ^
  tests\test_chain_assets.py ^
  tests\test_sse.py -q
```

Expected: selected backend tests pass.

- [ ] **Step 7: Run frontend focused tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm test -- --run src/api/sse.test.ts src/store/chatStore.test.ts src/components/chat/MessageBubble.test.tsx
```

Expected: selected frontend tests pass.

- [ ] **Step 8: Build corpus for manual vectorization**

Command for the user or implementer to run after code review:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
D:\Anaconda32024\envs\LangChain\python.exe scripts\build_huiji_corpus.py
```

Expected output includes:

```text
[huiji-corpus] parents=...
[huiji-corpus] children=...
[huiji-corpus] media=...
[huiji-corpus] excluded=...
```

Inspect outputs:

```powershell
Get-Content data\processed\huiji\dev\build_manifest.json
Get-Content data\processed\huiji\dev\excluded_entities.jsonl -TotalCount 20
```

- [ ] **Step 9: Rebuild Milvus v3 collection**

The user can delete stale `text_child_bge_m3_v3` if a partial build exists, then run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
D:\Anaconda32024\envs\LangChain\python.exe scripts\build_huiji_index.py
```

Expected output:

```text
[huiji-index] collection=reverse1999_rag.text_child_bge_m3_v3
[huiji-index] inserted .../...
[huiji-index] done: reverse1999_rag.text_child_bge_m3_v3
```

- [ ] **Step 10: Manual QA checks**

Start backend/frontend, then verify:

```text
介绍一下十四行诗
十四行诗的技能是什么
介绍一下十四行诗的单品
播放十四行诗语音
十四行诗有没有视频
介绍一下温妮弗雷德
```

Expected behavior:

- `介绍一下十四行诗` returns balanced character information, not only `profile`.
- `十四行诗的技能是什么` returns grouped skill star effects and skill images when available.
- `介绍一下十四行诗的单品` prefers item section and does not answer with unrelated story-only fragments.
- Voice questions render a voice panel.
- Video questions render a video panel.
- Placeholder `???` sources do not appear in visible source names.
- Rescue buttons appear only when no reliable grounded result is available.

---

## Self-Review Checklist

- Spec coverage: The plan covers entity packages, hierarchy, QueryPlan multi-route fields, policy registry, BM25+dense fusion, optional reranker, ancestor/sibling expansion, omitted actions, persistent and temporary input buttons, media attachment, voice panel, video panel, hard exclusions, quality flags, and future-safe v3 indexing.
- Data source boundary: The plan uses Huiji crawler data only for the QA system and does not add Obsidian ingestion.
- Vectorization boundary: The plan separates implementation from manual corpus/index rebuild commands.
- Type consistency: `entity_type`, `depth_level`, `ancestor_ids`, `quality_flags`, `route_tags`, `omitted_actions`, `failure_actions`, `route_options`, and `media_panels` are named consistently across backend and frontend tasks.
- Placeholder scan targets: The plan avoids unresolved placeholder markers and vague implementation instructions.
