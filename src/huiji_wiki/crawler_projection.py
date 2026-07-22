"""Project Huiji crawler records into canonical Wiki character content and media."""
from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote


_FORBIDDEN_SOURCE_MARKERS = ("obsidian", "wiki-supplement", "obsidian_character")
_RESOURCE_SUFFIXES = (".webp", ".png", ".jpg", ".jpeg")
_DAMAGE_TYPES = {1: "现实创伤", 2: "精神创伤"}


@dataclass(frozen=True)
class CrawlerProjectionConfig:
    public_base_url: str
    bucket_name: str
    object_prefix: str = "reverse1999"


@dataclass(frozen=True)
class CrawlerCharacterRecord:
    page_id: str
    source_title: str
    profile: dict[str, Any]
    blocks: tuple[dict[str, Any], ...]
    skins: tuple[dict[str, Any], ...]
    media_links: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class CrawlerCharacterProjection:
    characters: dict[str, CrawlerCharacterRecord]


def build_crawler_character_projection(
    raw_root: Path,
    *,
    config: CrawlerProjectionConfig,
) -> CrawlerCharacterProjection:
    root = Path(raw_root).resolve()
    data_pages = root / "data_pages.jsonl"
    resources_manifest = root / "resources_manifest.jsonl"
    if not data_pages.is_file() or not resources_manifest.is_file():
        raise FileNotFoundError("crawler data_pages.jsonl and resources_manifest.jsonl are required")

    resources = _ResourceIndex(root, _read_jsonl(resources_manifest))
    character_rows: list[tuple[str, dict[str, Any]]] = []
    item_rows: list[tuple[str, dict[str, Any]]] = []
    for row in _read_jsonl(data_pages):
        title = str(row.get("title") or "")
        content = _json_object(row.get("content"))
        if title.startswith("Data:Char/") and content:
            character_rows.append((title, content))
        elif title.startswith("Data:Item/") and content:
            item_rows.append((title, content))

    udimo_by_character = _index_udimo_items(item_rows)
    characters: dict[str, CrawlerCharacterRecord] = {}
    for source_title, content in character_rows:
        raw_entity_id = content.get("id")
        if not isinstance(raw_entity_id, (int, str)):
            continue
        entity_id = str(raw_entity_id).strip()
        if not entity_id.isdigit() or not _plain_text(content.get("name")):
            continue
        page_id = f"char:{entity_id}"
        record = _project_character(
            page_id=page_id,
            source_title=source_title,
            content=content,
            udimo=udimo_by_character.get(_normal_name(content.get("name"))),
            resources=resources,
            config=config,
        )
        validate_crawler_only_payload(record.__dict__)
        characters[page_id] = record
    return CrawlerCharacterProjection(characters=characters)


def validate_crawler_only_payload(payload: Any) -> None:
    for value in _walk_provenance_values(payload):
        lowered = value.casefold()
        if any(marker in lowered for marker in _FORBIDDEN_SOURCE_MARKERS):
            raise ValueError(f"crawler-only payload contains a legacy source marker: {value}")


def _project_character(
    *,
    page_id: str,
    source_title: str,
    content: dict[str, Any],
    udimo: tuple[str, dict[str, Any]] | None,
    resources: "_ResourceIndex",
    config: CrawlerProjectionConfig,
) -> CrawlerCharacterRecord:
    media_links: list[dict[str, Any]] = []
    skins: list[dict[str, Any]] = []
    media_order = 1
    default_skin_id = str(content.get("skinId") or "")

    for skin_index, skin_value in enumerate(_dict_items(content.get("skin")), start=1):
        skin_id = str(skin_value.get("id") or skin_index)
        skin_media_ids: dict[str, str] = {}
        explicit_resources = [
            ("roster_avatar", "roster", f"Headicon_large-{skin_value.get('largeIcon') or ''}"),
            ("stage_live2d", "stage", f"L2d_static-{skin_value.get('live2d') or ''}"),
            ("stage_portrait", "stage", f"L2d_static-{skin_value.get('verticalDrawing') or ''}"),
            ("skin_background", "skins", f"Skin_bg-{skin_value.get('live2dbg') or ''}"),
        ]
        for role, section_key, stem in explicit_resources:
            if stem.endswith("-"):
                continue
            if role == "roster_avatar" and default_skin_id and skin_id != default_skin_id:
                continue
            resource = resources.find(stem)
            if resource is None:
                continue
            link = _media_link(
                page_id=page_id,
                role=role,
                section_key=section_key,
                token=skin_id,
                variant=skin_id,
                order=media_order,
                resource=resource,
                config=config,
            )
            media_links.append(link)
            skin_media_ids[role] = link["media_id"]
            media_order += 1

        if "stage_portrait" not in skin_media_ids:
            drawing = str(skin_value.get("drawing") or "")
            resource = resources.find(f"Portrait-{drawing}") if drawing else None
            if resource is not None:
                link = _media_link(
                    page_id=page_id,
                    role="stage_portrait",
                    section_key="stage",
                    token=skin_id,
                    variant=skin_id,
                    order=media_order,
                    resource=resource,
                    config=config,
                )
                media_links.append(link)
                skin_media_ids["stage_portrait"] = link["media_id"]
                media_order += 1

        skins.append(
            {
                "id": skin_id,
                "name": _plain_text(skin_value.get("name")),
                "nameEng": _plain_text(skin_value.get("nameEng")),
                "description": _plain_text(
                    skin_value.get("skinDescription") or skin_value.get("des")
                ),
                "mediaIds": skin_media_ids,
            }
        )

    blocks: list[dict[str, Any]] = []
    blocks.extend(_progression_blocks(page_id, "inheritance", content.get("passive_skill")))
    blocks.extend(_progression_blocks(page_id, "portray", content.get("skill_ex_level")))

    collection_media_by_ordinal: dict[int, str] = {}
    for item in _dict_items(content.get("character_data")):
        if int(item.get("type") or 0) != 2:
            continue
        ordinal = int(item.get("number") or item.get("id") or 0)
        icon = str(item.get("icon") or "")
        resource = resources.find(f"Belonging-{icon}") if icon else None
        media_ids: list[str] = []
        if resource is not None:
            link = _media_link(
                page_id=page_id,
                role="collection_item",
                section_key="collection",
                token=f"{item.get('id') or ordinal}:{icon}",
                variant=str(item.get("skinId") or ""),
                order=media_order,
                resource=resource,
                config=config,
            )
            media_links.append(link)
            media_ids.append(link["media_id"])
            collection_media_by_ordinal[ordinal] = link["media_id"]
            media_order += 1
        blocks.append(
            _structured_block(
                page_id,
                "collection",
                f"collection:{item.get('id') or ordinal}",
                media_ids=media_ids,
                kind="collection_item",
                group="单品",
                groupEn="COLLECTION",
                ordinal=ordinal,
                name=_plain_text(item.get("title")),
                nameEn=_plain_text(item.get("titleEn")),
                value=_plain_text(item.get("estimate")),
                description=_plain_text(item.get("text")),
            )
        )

    for item in _dict_items(content.get("character_data")):
        if int(item.get("type") or 0) != 3:
            continue
        ordinal = int(item.get("number") or item.get("id") or 0)
        blocks.append(
            _structured_block(
                page_id,
                "culture_dossier",
                f"culture:{item.get('id') or ordinal}",
                ordinal=ordinal,
                title=_plain_text(item.get("title")),
                titleEn=_plain_text(item.get("titleEn")),
                tags=[],
                paragraphs=_paragraphs(item.get("text")),
            )
        )

    udimo_media_id = ""
    if udimo is not None:
        _, udimo_item = udimo
        icon = str(udimo_item.get("icon") or "")
        resource = resources.find(f"Item-{icon}") if icon else None
        if resource is not None:
            link = _media_link(
                page_id=page_id,
                role="udimo",
                section_key="summary",
                token=icon,
                variant="",
                order=media_order,
                resource=resource,
                config=config,
            )
            media_links.append(link)
            udimo_media_id = link["media_id"]

    profile = _build_profile(content, udimo)
    if udimo_media_id:
        profile["udimoMediaId"] = udimo_media_id
    return CrawlerCharacterRecord(
        page_id=page_id,
        source_title=source_title,
        profile=profile,
        blocks=tuple(blocks),
        skins=tuple(skins),
        media_links=tuple(media_links),
    )


def _build_profile(
    content: dict[str, Any],
    udimo: tuple[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    name = _plain_text(content.get("name"))
    exonym = _plain_text(content.get("nameEng"))
    passive = _dict_items(content.get("passive_skill"))
    skins = _dict_items(content.get("skin"))
    profile: dict[str, Any] = {
        "Name": name,
        "exonym": exonym,
        "aliases": [value for value in (name, exonym) if value],
        "星级": str(content.get("rare") or ""),
        "生日": _plain_text(content.get("roleBirthday")),
        "伤害类型": _DAMAGE_TYPES.get(int(content.get("dmgType") or 0), str(content.get("dmgType") or "")),
        "传承": _plain_text(passive[0].get("name")) if passive else "",
        "银行彩色相片": _plain_text(content.get("desc2")),
        "定位标签": _split_tokens(content.get("battleTag")),
    }
    if skins:
        profile["初始衣着"] = _plain_text(skins[0].get("skinDescription") or skins[0].get("des"))
    if len(skins) > 1:
        profile["洞悉本色"] = _plain_text(skins[1].get("skinDescription") or skins[1].get("des"))
    if udimo is not None:
        profile["Udimo"] = _plain_text(udimo[1].get("name"))
    return {key: value for key, value in profile.items() if value not in ("", [], None)}


def _progression_blocks(page_id: str, section: str, value: Any) -> list[dict[str, Any]]:
    rows = _dict_items(value)
    if not rows:
        return []
    if section == "inheritance":
        title = _plain_text(rows[0].get("name")) or "传承"
        description = _plain_text(rows[0].get("desc_art"))
        effects = [
            [str(row.get("skillLevel") or index), _plain_text(row.get("desc_art") or row.get("eff_desc"))]
            for index, row in enumerate(rows, start=1)
        ]
    else:
        title = "塑造"
        description = ""
        effects = [
            [str(row.get("skillLevel") or index), _plain_text(row.get("desc"))]
            for index, row in enumerate(rows, start=1)
        ]
    result = [
        _content_block(page_id, section, f"{section}:heading", "heading", level=2, text=title)
    ]
    if description:
        result.append(
            _content_block(
                page_id,
                section,
                f"{section}:description",
                "paragraph",
                text=description,
            )
        )
    result.append(
        _content_block(
            page_id,
            section,
            f"{section}:levels",
            "table",
            rows=[["等级", "效果"], *effects],
        )
    )
    return result


def _content_block(
    page_id: str,
    section: str,
    token: str,
    block_type: str,
    *,
    media_ids: Iterable[str] = (),
    **values: Any,
) -> dict[str, Any]:
    digest = hashlib.sha1(f"{page_id}|crawler|{section}|{token}".encode("utf-8")).hexdigest()[:16]
    return {
        "id": f"block:{digest}",
        "type": block_type,
        "section": section,
        "mediaIds": [str(item) for item in media_ids if item],
        **values,
    }


def _structured_block(
    page_id: str,
    section: str,
    token: str,
    *,
    media_ids: Iterable[str] = (),
    **values: Any,
) -> dict[str, Any]:
    return _content_block(
        page_id,
        section,
        token,
        "structured",
        media_ids=media_ids,
        **values,
    )


def _media_link(
    *,
    page_id: str,
    role: str,
    section_key: str,
    token: str,
    variant: str,
    order: int,
    resource: dict[str, Any],
    config: CrawlerProjectionConfig,
) -> dict[str, Any]:
    sha1 = str(resource["sha1"])
    suffix = Path(str(resource["name"])).suffix.lower()
    object_kind = "portrait" if role in {"roster_avatar", "stage_live2d", "stage_portrait"} else "image"
    prefix = config.object_prefix.strip("/")
    object_key = f"{prefix}/{object_kind}/{sha1[:2]}/{sha1}{suffix}"
    media_id = f"{page_id}/crawler:{role}:{token}"
    url = (
        f"{config.public_base_url.rstrip('/')}/{quote(config.bucket_name, safe='')}/"
        f"{quote(object_key, safe='/')}"
    )
    return {
        "page_id": page_id,
        "section_key": section_key,
        "media_id": media_id,
        "media_role": role,
        "display_order": order,
        "fallback_media_id": "",
        "object_key": object_key,
        "url": url,
        "asset_type": object_kind,
        "mime": str(resource.get("mime") or ""),
        "title": str(resource.get("title") or resource.get("name") or ""),
        "sha1": sha1,
        "width": int(resource.get("width") or 0),
        "height": int(resource.get("height") or 0),
        "variant": variant,
        "local_relpath": str(resource.get("local_relpath") or ""),
        "source_kind": "huiji_crawler",
    }


class _ResourceIndex:
    def __init__(self, root: Path, rows: Iterable[dict[str, Any]]) -> None:
        self.root = root
        self.by_name: dict[str, dict[str, Any]] = {}
        self.validated: dict[str, dict[str, Any] | None] = {}
        for row in rows:
            name = str(row.get("name") or Path(str(row.get("local_relpath") or "")).name)
            sha1 = str(row.get("sha1") or "").lower()
            relpath = str(row.get("local_relpath") or "")
            if not name or not re.fullmatch(r"[0-9a-f]{40}", sha1) or not relpath:
                continue
            self.by_name[name.casefold()] = {**row, "name": name, "sha1": sha1}

    def find(self, stem: str) -> dict[str, Any] | None:
        normalized = stem.strip()
        if not normalized:
            return None
        for suffix in _RESOURCE_SUFFIXES:
            key = f"{normalized}{suffix}".casefold()
            if key in self.validated:
                record = self.validated[key]
                if record is not None:
                    return record
                continue
            record = self.by_name.get(key)
            if record is None:
                continue
            path = (self.root / str(record.get("local_relpath") or "")).resolve()
            try:
                path.relative_to(self.root)
            except ValueError:
                self.validated[key] = None
                continue
            if not path.is_file() or _file_sha1(path) != str(record["sha1"]):
                self.validated[key] = None
                continue
            self.validated[key] = record
            return record
        return None


def _index_udimo_items(
    rows: Iterable[tuple[str, dict[str, Any]]],
) -> dict[str, tuple[str, dict[str, Any]]]:
    result: dict[str, tuple[str, dict[str, Any]]] = {}
    for source_title, item in rows:
        name = _plain_text(item.get("name"))
        for prefix in ("尤提姆贴纸·", "尤提姆·"):
            if not name.startswith(prefix):
                continue
            character_name = _normal_name(name[len(prefix):])
            if not character_name:
                continue
            current = result.get(character_name)
            if current is None or (not current[1].get("icon") and item.get("icon")):
                result[character_name] = (source_title, item)
    return result


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid crawler JSONL at {path}:{line_number}") from exc
            if isinstance(row, dict):
                yield row


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _dict_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _plain_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\{\{(?:s|sk)\|([^}|]+)(?:<id:[^>]+>)?[^}]*}}", r"\1", text)
    return html.unescape(text).replace("\r\n", "\n").strip()


def _paragraphs(value: Any) -> list[str]:
    text = _plain_text(value)
    return [part.strip() for part in re.split(r"\n+", text) if part.strip()]


def _split_tokens(value: Any) -> list[str]:
    return [part.strip() for part in re.split(r"[|,，/]+", str(value or "")) if part.strip()]


def _normal_name(value: Any) -> str:
    return re.sub(r"\s+", "", _plain_text(value)).casefold()


def _entity_id_from_title(title: str) -> str:
    match = re.fullmatch(r"Data:Char/([^/]+)\.json", title)
    return match.group(1) if match else ""


def _file_sha1(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _walk_provenance_values(value: Any, *, inherited: bool = False) -> Iterable[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).replace("-", "_").casefold()
            is_provenance = inherited or normalized.startswith("source") or normalized in {
                "object_key",
                "objectkey",
                "local_relpath",
                "localrelpath",
            }
            yield from _walk_provenance_values(item, inherited=is_provenance)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _walk_provenance_values(item, inherited=inherited)
    elif inherited and isinstance(value, str):
        yield value
