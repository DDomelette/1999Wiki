"""Bounded offline Wikitext scanning and deterministic Page projection."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from urllib.parse import parse_qs, unquote, urlsplit
from dataclasses import asdict, dataclass, field
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from .page_sources import JsonlRow, PageRevisionJoin


_HEADING_RE = re.compile(r"^(={2,6})[ \t]*(.*?)[ \t]*\1[ \t]*$")
_REDIRECT_RE = re.compile(
    r"^[ \t]*#(?:redirect|重定向|重定向至)[ \t]*\[\[(.*?)\]\]",
    re.IGNORECASE,
)
_FILE_PREFIXES = ("file:", "文件:", "image:", "图像:")
_LAYOUT_OPTIONS = frozenset(
    {"thumb", "frame", "frameless", "left", "right", "center", "none"}
)
_SIZE_RE = re.compile(r"(?:\d+(?:x\d+)?|x\d+)px\Z", re.IGNORECASE)
_DEFINITION_RE = re.compile(r"(?:\bis\b|\bare\b|是|指的是|定义为)", re.IGNORECASE)
_IMAGE_URL_RE = re.compile(r"https?://\S+\.(?:png|jpe?g|gif|webp|svg)(?:\?\S*)?", re.IGNORECASE)
_DECORATIVE_MINIMUM_DIMENSION_PX = 96
_PARSER_CONFIG_SHA256 = hashlib.sha256(
    json.dumps(
        {
            "decorative_minimum_dimension_px": _DECORATIVE_MINIMUM_DIMENSION_PX,
            "schema_version": "huiji.wikitext-media-parser/v1",
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()


@dataclass(frozen=True)
class WikitextDiagnostic:
    reason_code: str
    char_start: int
    char_end: int
    heading_path: tuple[str, ...] = ()
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "heading_path", tuple(self.heading_path))
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))


@dataclass(frozen=True)
class WikitextLink:
    target: str
    label: str
    heading_path: tuple[str, ...]
    char_start: int
    char_end: int


@dataclass(frozen=True)
class WikitextImage:
    filename: str
    source_kind: str
    caption: str
    alt: str
    link_target: str
    layout_options: tuple[str, ...]
    unknown_options: tuple[str, ...]
    heading_path: tuple[str, ...]
    char_start: int
    char_end: int


@dataclass(frozen=True)
class WikitextBlock:
    visible_text: str
    char_start: int
    char_end: int
    has_non_link_text: bool


@dataclass(frozen=True)
class WikitextSection:
    heading_path: tuple[str, ...]
    level: int
    char_start: int
    char_end: int
    visible_text: str
    blocks: tuple[WikitextBlock, ...]
    links: tuple[WikitextLink, ...]
    images: tuple[WikitextImage, ...]


@dataclass(frozen=True)
class WikitextScan:
    sections: tuple[WikitextSection, ...]
    links: tuple[WikitextLink, ...]
    images: tuple[WikitextImage, ...]
    display_titles: tuple[str, ...]
    redirect_targets: tuple[str, ...]
    diagnostics: tuple[WikitextDiagnostic, ...]


@dataclass(frozen=True)
class PageDiagnostic:
    reason_code: str
    pageid: int
    source_title: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))


@dataclass(frozen=True)
class PageExclusion:
    reason_code: str
    pageid: int
    source_title: str


@dataclass(frozen=True)
class PageParentProjection:
    parent_id: str
    entity_id: str
    entity_name: str
    entity_aliases: tuple[str, ...]
    child_ids: tuple[str, ...]
    source_refs: tuple[dict[str, Any], ...]
    content_hash: str

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PageSectionProjection:
    parent_id: str
    root_parent_id: str
    heading_path: tuple[str, ...]
    child_ids: tuple[str, ...]
    source_refs: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class PageChildProjection:
    category: str
    entity_type: str
    entity_id: str
    entity_name: str
    entity_aliases: tuple[str, ...]
    owner_entity_id: str
    owner_page_id: str
    route_tags: tuple[str, ...]
    parent_id: str
    child_id: str
    heading_path: tuple[str, ...]
    section_kind: str
    content: str
    text: str
    search_text: str
    source_refs: tuple[dict[str, Any], ...]
    quality_flags: tuple[str, ...]
    content_hash: str

    def to_json(self) -> dict[str, Any]:
        row = asdict(self)
        row.pop("quality_flags")
        row.pop("content_hash")
        return row


@dataclass(frozen=True)
class PageImageReference:
    image: WikitextImage
    pageid: int
    revid: int
    source_title: str
    owner_entity_id: str
    owner_page_id: str
    parent_id: str
    child_id: str
    source_ref: Mapping[str, Any]

    def __post_init__(self) -> None:
        source_ref = dict(self.source_ref)
        source_ref["heading_path"] = tuple(source_ref.get("heading_path", ()))
        object.__setattr__(self, "source_ref", MappingProxyType(source_ref))

    def to_json(self) -> dict[str, Any]:
        source_ref = dict(self.source_ref)
        source_ref["heading_path"] = list(source_ref["heading_path"])
        return {
            "image": asdict(self.image),
            "pageid": self.pageid,
            "revid": self.revid,
            "source_title": self.source_title,
            "owner_entity_id": self.owner_entity_id,
            "owner_page_id": self.owner_page_id,
            "parent_id": self.parent_id,
            "child_id": self.child_id,
            "source_ref": source_ref,
        }


@dataclass(frozen=True)
class WikitextMediaIntent:
    source_binding_token: str
    owner_entity_id: str
    owner_page_id: str
    parent_id: str
    child_id: str
    heading_path: tuple[str, ...]
    normalized_filename: str
    original_filename: str
    source_kind: str
    occurrence: int
    media_role: str
    title: str
    title_source: str
    caption: str
    alt: str
    link_target: str
    layout_options: tuple[str, ...]
    unknown_options: tuple[str, ...]
    source_ref: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "heading_path", tuple(self.heading_path))
        object.__setattr__(self, "layout_options", tuple(self.layout_options))
        object.__setattr__(self, "unknown_options", tuple(self.unknown_options))
        source_ref = dict(self.source_ref)
        source_ref["heading_path"] = tuple(source_ref.get("heading_path", ()))
        object.__setattr__(self, "source_ref", MappingProxyType(source_ref))


@dataclass(frozen=True)
class PageProjection:
    pages: tuple[PageParentProjection, ...]
    sections: tuple[PageSectionProjection, ...]
    children: tuple[PageChildProjection, ...]
    image_references: tuple[PageImageReference, ...]
    media_intents: tuple[WikitextMediaIntent, ...]
    redirects: tuple[tuple[str, str], ...]
    diagnostics: tuple[PageDiagnostic, ...]
    exclusions: tuple[PageExclusion, ...]


@dataclass
class _SectionBuilder:
    heading_path: tuple[str, ...]
    level: int
    char_start: int
    char_end: int
    blocks: list[WikitextBlock] = field(default_factory=list)
    links: list[WikitextLink] = field(default_factory=list)
    images: list[WikitextImage] = field(default_factory=list)


def scan_wikitext(content: str) -> WikitextScan:
    """Scan only the frozen P0 syntax without external calls or template expansion."""
    text = str(content)
    sections: list[_SectionBuilder] = [_SectionBuilder((), 1, 0, len(text))]
    heading_stack: list[str] = []
    links: list[WikitextLink] = []
    images: list[WikitextImage] = []
    display_titles: list[str] = []
    redirects: list[str] = []
    diagnostics: list[WikitextDiagnostic] = []
    paragraph_lines: list[tuple[str, int, int, bool]] = []
    in_gallery = False
    gallery_start = 0
    gallery_lines: list[tuple[str, int, int]] = []

    def current() -> _SectionBuilder:
        return sections[-1]

    def flush_paragraph() -> None:
        if not paragraph_lines:
            return
        visible = "\n".join(item[0] for item in paragraph_lines if item[0]).strip()
        if visible:
            current().blocks.append(
                WikitextBlock(
                    visible_text=visible,
                    char_start=paragraph_lines[0][1],
                    char_end=paragraph_lines[-1][2],
                    has_non_link_text=any(item[3] for item in paragraph_lines),
                )
            )
        paragraph_lines.clear()

    offset = 0
    for raw_line in text.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        line_end = offset + len(line)
        heading_match = _HEADING_RE.fullmatch(line)

        if in_gallery and (
            line.strip().casefold() == "</gallery>" or heading_match is not None
        ):
            _consume_gallery(
                gallery_lines,
                current(),
                images,
                diagnostics,
            )
            gallery_lines.clear()
            if heading_match is not None:
                diagnostics.append(
                    WikitextDiagnostic(
                        "unclosed_gallery",
                        gallery_start,
                        offset,
                        current().heading_path,
                    )
                )
            in_gallery = False
            if line.strip().casefold() == "</gallery>":
                offset += len(raw_line)
                continue

        if heading_match is not None:
            flush_paragraph()
            current().char_end = offset
            level = len(heading_match.group(1))
            heading_visible, _, _, _ = _scan_inline(
                heading_match.group(2),
                offset + line.find(heading_match.group(2)),
                current().heading_path,
                diagnostics,
                display_titles,
            )
            heading = heading_visible.strip()
            heading_stack[level - 2 :] = [heading]
            heading_path = tuple(heading_stack)
            sections.append(_SectionBuilder(heading_path, level, offset + len(raw_line), len(text)))
            offset += len(raw_line)
            continue

        if line.strip().casefold() == "<gallery>":
            flush_paragraph()
            in_gallery = True
            gallery_start = offset
            offset += len(raw_line)
            continue
        if in_gallery:
            gallery_lines.append((line, offset, line_end))
            offset += len(raw_line)
            continue

        redirect_match = _REDIRECT_RE.match(line)
        if redirect_match:
            flush_paragraph()
            redirects.append(_split_top_level(redirect_match.group(1), "|")[0].strip())
            offset += len(raw_line)
            continue

        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            offset += len(raw_line)
            continue
        if stripped.startswith("{|") or stripped in {"|-", "|}"}:
            flush_paragraph()
            offset += len(raw_line)
            continue
        if stripped.startswith(("!", "|")):
            flush_paragraph()
            separator = "!!" if stripped.startswith("!") else "||"
            cells = [_strip_table_cell(item) for item in stripped[1:].split(separator)]
            visible = " | ".join(item for item in cells if item)
            if visible:
                current().blocks.append(WikitextBlock(visible, offset, line_end, True))
            offset += len(raw_line)
            continue

        visible, line_links, line_images, has_plain = _scan_inline(
            line,
            offset,
            current().heading_path,
            diagnostics,
            display_titles,
        )
        current().links.extend(line_links)
        current().images.extend(line_images)
        links.extend(line_links)
        images.extend(line_images)
        if visible.strip():
            paragraph_lines.append((visible.strip(), offset, line_end, has_plain))
        if _IMAGE_URL_RE.search(line):
            diagnostics.append(
                WikitextDiagnostic(
                    "unsupported_html_media",
                    offset,
                    line_end,
                    current().heading_path,
                    {"mode": "bare_image_url"},
                )
            )
        offset += len(raw_line)

    if in_gallery:
        _consume_gallery(gallery_lines, current(), images, diagnostics)
        diagnostics.append(
            WikitextDiagnostic(
                "unclosed_gallery",
                gallery_start,
                len(text),
                current().heading_path,
            )
        )
    flush_paragraph()
    current().char_end = len(text)
    frozen_sections = tuple(
        WikitextSection(
            heading_path=item.heading_path,
            level=item.level,
            char_start=item.char_start,
            char_end=item.char_end,
            visible_text="\n".join(block.visible_text for block in item.blocks),
            blocks=tuple(item.blocks),
            links=tuple(item.links),
            images=tuple(item.images),
        )
        for item in sections
    )
    return WikitextScan(
        sections=frozen_sections,
        links=tuple(links),
        images=tuple(images),
        display_titles=tuple(dict.fromkeys(display_titles)),
        redirect_targets=tuple(redirects),
        diagnostics=tuple(diagnostics),
    )


def normalize_wikitext_filename(value: str) -> str:
    """Normalize a complete Wikitext filename without stem or fuzzy matching."""
    raw = str(value).strip()
    parsed = urlsplit(raw)
    if parsed.scheme and parsed.netloc:
        query_title = parse_qs(parsed.query).get("title", ())
        raw = query_title[0] if query_title else parsed.path.rsplit("/", 1)[-1]
    raw = unicodedata.normalize("NFKC", unquote(raw)).strip()
    folded = raw.casefold()
    for prefix in ("file:", "image:", "文件:", "图像:"):
        if folded.startswith(prefix.casefold()):
            raw = raw[len(prefix) :].strip()
            break
    raw = re.sub(r"[ _]+", "_", raw)
    stem, separator, extension = raw.rpartition(".")
    if separator and stem and extension:
        return f"{stem}.{extension.lower()}"
    return raw


def project_wikitext_pages(
    page_join: PageRevisionJoin,
    revision_rows: Iterable[JsonlRow],
    *,
    structured_route_tags: Mapping[int, Sequence[str]] | None = None,
) -> PageProjection:
    """Project joined revisions in deterministic page order."""
    joined = {(item.page.pageid, item.revision.revid): item for item in page_join.joined}
    scans: dict[int, tuple[Any, JsonlRow, WikitextScan]] = {}
    diagnostics: list[PageDiagnostic] = []
    for item in revision_rows:
        row = item.row
        key = (int(row["pageid"]), int(row["revid"]))
        match = joined.get(key)
        if match is None:
            continue
        if str(row.get("title") or "") != match.page.title:
            continue
        scan = scan_wikitext(str(row.get("content") or ""))
        scans[match.page.pageid] = (match, item, scan)
        diagnostics.extend(
            PageDiagnostic(diag.reason_code, match.page.pageid, match.page.title)
            for diag in scan.diagnostics
        )

    title_to_pageid = {
        item.page.title: item.page.pageid for item in page_join.joined if item.page.pageid in scans
    }
    redirect_targets: dict[int, str] = {}
    invalid_redirects: set[int] = set()
    for pageid, (joined_item, _, scan) in sorted(scans.items()):
        if not scan.redirect_targets:
            continue
        if len(set(scan.redirect_targets)) != 1:
            invalid_redirects.add(pageid)
            diagnostics.append(
                PageDiagnostic("conflicting_redirect", pageid, joined_item.page.title)
            )
            continue
        target = scan.redirect_targets[0]
        if ":" in target:
            invalid_redirects.add(pageid)
            diagnostics.append(
                PageDiagnostic("cross_namespace_redirect", pageid, joined_item.page.title)
            )
            continue
        if target not in title_to_pageid:
            invalid_redirects.add(pageid)
            diagnostics.append(
                PageDiagnostic("dangling_redirect", pageid, joined_item.page.title)
            )
            continue
        redirect_targets[pageid] = target

    cycles = _redirect_cycles(redirect_targets, title_to_pageid)
    for pageid in sorted(cycles):
        invalid_redirects.add(pageid)
        diagnostics.append(PageDiagnostic("redirect_cycle", pageid, scans[pageid][0].page.title))

    aliases: dict[int, list[str]] = {}
    redirects: list[tuple[str, str]] = []
    for pageid, target in sorted(redirect_targets.items()):
        if pageid in invalid_redirects:
            continue
        destination = _resolve_redirect_target(target, redirect_targets, title_to_pageid)
        if destination is None:
            continue
        alias = scans[pageid][0].page.title
        aliases.setdefault(destination, []).append(alias)
        redirects.append((alias, scans[destination][0].page.title))

    pages: list[PageParentProjection] = []
    sections: list[PageSectionProjection] = []
    children: list[PageChildProjection] = []
    image_references: list[PageImageReference] = []
    media_intents: list[WikitextMediaIntent] = []
    exclusions: list[PageExclusion] = []
    route_evidence = structured_route_tags or {}
    redirect_pageids = {pageid for pageid, (_, _, scan) in scans.items() if scan.redirect_targets}

    for pageid, (joined_item, source_row, scan) in sorted(scans.items()):
        if pageid in redirect_pageids:
            continue
        entity_aliases = tuple(
            sorted(
                set(aliases.get(pageid, ())) | set(scan.display_titles),
                key=lambda value: (value.casefold(), value),
            )
        )
        page_children: list[PageChildProjection] = []
        section_occurrences: dict[str, int] = {}
        media_occurrences: dict[tuple[str, str], int] = {}
        source_content = str(source_row.row.get("content") or "")
        source_content_sha256 = str(
            source_row.row.get("content_sha256")
            or joined_item.revision.content_sha256
        )
        for section in scan.sections:
            if not section.visible_text and not section.links and not section.images:
                continue
            section_token, occurrence = _section_token(
                section.heading_path, section_occurrences
            )
            if occurrence > 1:
                diagnostics.append(
                    PageDiagnostic(
                        "duplicate_heading_path_occurrence",
                        pageid,
                        joined_item.page.title,
                        {"occurrence": occurrence, "heading_depth": len(section.heading_path)},
                    )
                )
            section_parent_id = f"page:{pageid}/section:{section_token}"
            chunks = _chunk_section(section)
            section_children: list[PageChildProjection] = []
            for chunk_index, (chunk_text, char_start, char_end, has_plain) in enumerate(chunks):
                heading_path = section.heading_path or ("lead",)
                route_tags = ["page"]
                if _DEFINITION_RE.search(chunk_text):
                    route_tags.append("definition")
                for tag in ("story", "event"):
                    if tag in route_evidence.get(pageid, ()):
                        route_tags.append(tag)
                quality_flags = (
                    ("sparse_text",)
                    if not has_plain and (section.links or section.images)
                    else ()
                )
                child_id = f"{section_parent_id}/chunk:{chunk_index:04d}"
                source_ref = _source_ref(
                    joined_item.page.title,
                    pageid,
                    joined_item.revision.revid,
                    str(source_row.row.get("content_sha256") or joined_item.revision.content_sha256),
                    heading_path,
                    char_start,
                    char_end,
                )
                link_labels = " ".join(link.label for link in section.links)
                search_text = " ".join(
                    value
                    for value in (
                        joined_item.page.title,
                        " ".join(entity_aliases),
                        " ".join(heading_path),
                        link_labels,
                        chunk_text,
                    )
                    if value
                )
                child = PageChildProjection(
                    category="page",
                    entity_type="page",
                    entity_id=f"page:{pageid}",
                    entity_name=joined_item.page.title,
                    entity_aliases=entity_aliases,
                    owner_entity_id=f"page:{pageid}",
                    owner_page_id=f"page:{pageid}",
                    route_tags=tuple(route_tags),
                    parent_id=section_parent_id,
                    child_id=child_id,
                    heading_path=heading_path,
                    section_kind="lead" if not section.heading_path else "section",
                    content=chunk_text,
                    text=chunk_text,
                    search_text=search_text,
                    source_refs=(source_ref,),
                    quality_flags=quality_flags,
                    content_hash=hashlib.sha256(chunk_text.encode("utf-8")).hexdigest(),
                )
                section_children.append(child)
                page_children.append(child)
            sections.append(
                PageSectionProjection(
                    parent_id=section_parent_id,
                    root_parent_id=f"page:{pageid}",
                    heading_path=section.heading_path or ("lead",),
                    child_ids=tuple(child.child_id for child in section_children),
                    source_refs=tuple(
                        child.source_refs[0] for child in section_children[:1]
                    ),
                )
            )
            for image in section.images:
                context_before, context_after = _adjacent_context(
                    source_content,
                    section,
                    image,
                )
                binding_child = _image_binding_child(
                    image,
                    section_children,
                    context_before,
                    context_after,
                )
                context_before, context_after = _context_for_child(
                    binding_child,
                    image,
                    context_before,
                    context_after,
                )
                image_source_ref = _source_ref(
                    joined_item.page.title,
                    pageid,
                    joined_item.revision.revid,
                    source_content_sha256,
                    image.heading_path or ("lead",),
                    image.char_start,
                    image.char_end,
                )
                image_references.append(
                    PageImageReference(
                        image=image,
                        pageid=pageid,
                        revid=joined_item.revision.revid,
                        source_title=joined_item.page.title,
                        owner_entity_id=f"page:{pageid}",
                        owner_page_id=f"page:{pageid}",
                        parent_id=section_parent_id,
                        child_id=binding_child.child_id,
                        source_ref=image_source_ref,
                    )
                )
                declared_width, declared_height = _declared_dimensions(
                    image.layout_options
                )
                if (
                    0 < declared_width < _DECORATIVE_MINIMUM_DIMENSION_PX
                    and 0 < declared_height < _DECORATIVE_MINIMUM_DIMENSION_PX
                ):
                    diagnostics.append(
                        PageDiagnostic(
                            "decorative_media_excluded",
                            pageid,
                            joined_item.page.title,
                            {
                                "declared_width": declared_width,
                                "declared_height": declared_height,
                                "minimum_dimension_px": (
                                    _DECORATIVE_MINIMUM_DIMENSION_PX
                                ),
                                "parser_config_sha256": _PARSER_CONFIG_SHA256,
                            },
                        )
                    )
                    continue
                normalized_filename = normalize_wikitext_filename(image.filename)
                occurrence_key = (section_parent_id, normalized_filename)
                media_occurrences[occurrence_key] = (
                    media_occurrences.get(occurrence_key, 0) + 1
                )
                media_occurrence = media_occurrences[occurrence_key]
                title, title_source = _media_display_title(
                    image,
                    section,
                    joined_item.page.title,
                    source_content,
                    normalized_filename,
                )
                context_sha256 = hashlib.sha256(
                    f"{context_before}\0{context_after}".encode("utf-8")
                ).hexdigest()
                media_source_ref = {
                    **image_source_ref,
                    "original_filename": image.filename,
                    "normalized_filename": normalized_filename,
                    "original_caption": image.caption,
                    "alt": image.alt,
                    "link_target": image.link_target,
                    "display_title_source": title_source,
                    "context_before": context_before,
                    "context_after": context_after,
                    "adjacent_context_sha256": context_sha256,
                    "layout_options": tuple(image.layout_options),
                    "unknown_options": tuple(image.unknown_options),
                    "source_kind_detail": image.source_kind,
                }
                filename_sha20 = hashlib.sha256(
                    normalized_filename.encode("utf-8")
                ).hexdigest()[:20]
                relation_token = (
                    f"wiki:{pageid}:{section_token}:{filename_sha20}"
                )
                if media_occurrence > 1:
                    relation_token = f"{relation_token}:{media_occurrence}"
                media_intents.append(
                    WikitextMediaIntent(
                        source_binding_token=relation_token,
                        owner_entity_id=f"page:{pageid}",
                        owner_page_id=f"page:{pageid}",
                        parent_id=section_parent_id,
                        child_id=binding_child.child_id,
                        heading_path=image.heading_path or ("lead",),
                        normalized_filename=normalized_filename,
                        original_filename=image.filename,
                        source_kind=image.source_kind,
                        occurrence=media_occurrence,
                        media_role=_wikitext_media_role(
                            image,
                            section,
                            declared_width,
                            declared_height,
                        ),
                        title=title,
                        title_source=title_source,
                        caption=image.caption,
                        alt=image.alt,
                        link_target=image.link_target,
                        layout_options=image.layout_options,
                        unknown_options=image.unknown_options,
                        source_ref=media_source_ref,
                    )
                )
        if not page_children:
            exclusions.append(PageExclusion("empty_page", pageid, joined_item.page.title))
            continue
        root_ref = _source_ref(
            joined_item.page.title,
            pageid,
            joined_item.revision.revid,
            str(source_row.row.get("content_sha256") or joined_item.revision.content_sha256),
            ("lead",),
            0,
            len(str(source_row.row.get("content") or "")),
        )
        pages.append(
            PageParentProjection(
                parent_id=f"page:{pageid}",
                entity_id=f"page:{pageid}",
                entity_name=joined_item.page.title,
                entity_aliases=entity_aliases,
                child_ids=tuple(child.child_id for child in page_children),
                source_refs=(root_ref,),
                content_hash=hashlib.sha256(
                    "\n".join(child.content_hash for child in page_children).encode("utf-8")
                ).hexdigest(),
            )
        )
        children.extend(page_children)

    diagnostics.sort(key=lambda item: (item.pageid, item.reason_code))
    return PageProjection(
        pages=tuple(pages),
        sections=tuple(sections),
        children=tuple(children),
        image_references=tuple(
            sorted(
                image_references,
                key=lambda item: (
                    item.pageid,
                    item.revid,
                    item.image.char_start,
                    item.image.char_end,
                    item.image.filename.casefold(),
                    item.image.filename,
                ),
            )
        ),
        media_intents=tuple(media_intents),
        redirects=tuple(sorted(redirects)),
        diagnostics=tuple(diagnostics),
        exclusions=tuple(sorted(exclusions, key=lambda item: item.pageid)),
    )


def _declared_dimensions(options: Sequence[str]) -> tuple[int, int]:
    for option in options:
        folded = option.casefold()
        if not _SIZE_RE.fullmatch(folded):
            continue
        value = folded[:-2]
        if "x" in value:
            width_text, height_text = value.split("x", 1)
            return (
                int(width_text) if width_text else 0,
                int(height_text) if height_text else 0,
            )
        dimension = int(value)
        return dimension, dimension
    return 0, 0


def _media_display_title(
    image: WikitextImage,
    section: WikitextSection,
    page_title: str,
    source_content: str,
    normalized_filename: str,
) -> tuple[str, str]:
    if image.caption:
        return image.caption, "explicit_caption"
    adjacent = _adjacent_link_label(image, section.links, source_content)
    if adjacent:
        return adjacent, "adjacent_link_label"
    if image.heading_path:
        return image.heading_path[-1], "heading"
    if page_title:
        return page_title, "page_title"
    return normalized_filename, "filename_fallback"


def _adjacent_link_label(
    image: WikitextImage,
    links: Sequence[WikitextLink],
    source_content: str,
) -> str:
    candidates: list[tuple[int, int, str]] = []
    for link in links:
        if link.char_end <= image.char_start:
            gap = source_content[link.char_end : image.char_start]
            distance = image.char_start - link.char_end
        elif image.char_end <= link.char_start:
            gap = source_content[image.char_end : link.char_start]
            distance = link.char_start - image.char_end
        else:
            continue
        if distance <= 80 and not gap.strip(" \t\r\n.,;:()[]"):
            candidates.append((distance, link.char_start, link.label))
    return min(candidates)[2] if candidates else ""


def _adjacent_context(
    source_content: str,
    section: WikitextSection,
    image: WikitextImage,
) -> tuple[str, str]:
    before_raw = source_content[section.char_start : image.char_start]
    after_raw = source_content[image.char_end : section.char_end]
    before = _visible_fragment(before_raw).strip()[-200:]
    after = _visible_fragment(after_raw).strip()[:200]
    return before, after


def _visible_fragment(value: str) -> str:
    visible, _, _, _ = _scan_inline(value, 0, (), [], [])
    return visible


def _wikitext_media_role(
    image: WikitextImage,
    section: WikitextSection,
    declared_width: int,
    declared_height: int,
) -> str:
    if image.source_kind == "gallery":
        return "gallery_image"
    caption_heading = " ".join((image.caption, *image.heading_path)).casefold()
    if "poster" in caption_heading or "海报" in caption_heading:
        return "poster"
    is_lead = not section.heading_path
    is_large = max(declared_width, declared_height) >= 600
    has_banner_layout = "center" in {
        option.casefold() for option in image.layout_options
    } and max(declared_width, declared_height) >= 300
    if is_lead and (is_large or has_banner_layout):
        return "banner"
    return "page_image"


def _scan_inline(
    text: str,
    absolute_start: int,
    heading_path: tuple[str, ...],
    diagnostics: list[WikitextDiagnostic],
    display_titles: list[str],
) -> tuple[str, list[WikitextLink], list[WikitextImage], bool]:
    visible: list[str] = []
    links: list[WikitextLink] = []
    images: list[WikitextImage] = []
    has_plain = False
    index = 0
    while index < len(text):
        if text.startswith("[[", index):
            end = _balanced_end(text, index, "[[", "]]")
            if end is None:
                diagnostics.append(
                    WikitextDiagnostic(
                        "unbalanced_wikilink",
                        absolute_start + index,
                        absolute_start + len(text),
                        heading_path,
                    )
                )
                break
            inner = text[index + 2 : end - 2]
            parts = _split_top_level(inner, "|")
            target = parts[0].strip()
            if _is_file_target(target):
                image = _image_from_parts(
                    target,
                    parts[1:],
                    "file_link",
                    heading_path,
                    absolute_start + index,
                    absolute_start + end,
                )
                images.append(image)
                if image.unknown_options:
                    diagnostics.append(
                        WikitextDiagnostic(
                            "unknown_image_option",
                            absolute_start + index,
                            absolute_start + end,
                            heading_path,
                            {"count": len(image.unknown_options)},
                        )
                    )
                if image.caption:
                    visible.append(image.caption)
            elif target.casefold().startswith(("category:", "分类:")):
                pass
            else:
                label_source = parts[-1].strip() if len(parts) > 1 else target
                label, nested_links, nested_images, _ = _scan_inline(
                    label_source,
                    absolute_start + index + 2 + inner.rfind(label_source),
                    heading_path,
                    diagnostics,
                    display_titles,
                )
                label = label.strip() or target
                link = WikitextLink(
                    target=target,
                    label=label,
                    heading_path=heading_path,
                    char_start=absolute_start + index,
                    char_end=absolute_start + end,
                )
                links.append(link)
                links.extend(nested_links)
                images.extend(nested_images)
                visible.append(label)
            index = end
            continue
        if text.startswith("{{", index):
            end = _balanced_end(text, index, "{{", "}}")
            if end is None:
                diagnostics.append(
                    WikitextDiagnostic(
                        "unsupported_template_media",
                        absolute_start + index,
                        absolute_start + len(text),
                        heading_path,
                    )
                )
                break
            inner = text[index + 2 : end - 2].strip()
            alias = _simple_display_title(inner)
            if alias:
                display_titles.append(alias)
            elif inner.casefold().startswith(("displaytitle", "displaytitle:")):
                diagnostics.append(
                    WikitextDiagnostic(
                        "dynamic_display_title",
                        absolute_start + index,
                        absolute_start + end,
                        heading_path,
                    )
                )
            else:
                diagnostics.append(
                    WikitextDiagnostic(
                        "unsupported_template_media",
                        absolute_start + index,
                        absolute_start + end,
                        heading_path,
                    )
                )
            index = end
            continue
        if text[index] == "<":
            close = text.find(">", index + 1)
            if close != -1:
                diagnostics.append(
                    WikitextDiagnostic(
                        "unsupported_html_media",
                        absolute_start + index,
                        absolute_start + close + 1,
                        heading_path,
                    )
                )
                index = close + 1
                continue
        visible.append(text[index])
        if not text[index].isspace():
            has_plain = True
        index += 1
    return "".join(visible), links, images, has_plain


def _balanced_end(text: str, start: int, opener: str, closer: str) -> int | None:
    depth = 0
    index = start
    while index < len(text):
        if text.startswith(opener, index):
            depth += 1
            index += len(opener)
            continue
        if text.startswith(closer, index):
            depth -= 1
            index += len(closer)
            if depth == 0:
                return index
            continue
        index += 1
    return None


def _split_top_level(text: str, separator: str) -> list[str]:
    parts: list[str] = []
    start = 0
    link_depth = 0
    template_depth = 0
    index = 0
    while index < len(text):
        if text.startswith("[[", index):
            link_depth += 1
            index += 2
            continue
        if text.startswith("]]", index) and link_depth:
            link_depth -= 1
            index += 2
            continue
        if text.startswith("{{", index):
            template_depth += 1
            index += 2
            continue
        if text.startswith("}}", index) and template_depth:
            template_depth -= 1
            index += 2
            continue
        if text.startswith(separator, index) and not link_depth and not template_depth:
            parts.append(text[start:index])
            index += len(separator)
            start = index
            continue
        index += 1
    parts.append(text[start:])
    return parts


def _simple_display_title(inner: str) -> str:
    folded = inner.casefold()
    value = ""
    if folded.startswith("displaytitle|"):
        value = inner.split("|", 1)[1].strip()
    if not value or any(token in value for token in ("{{", "}}", "[[", "]]", "<", ">")):
        return ""
    return value if "|" not in value else ""


def _is_file_target(target: str) -> bool:
    return target.casefold().startswith(_FILE_PREFIXES)


def _strip_file_prefix(target: str) -> str:
    folded = target.casefold()
    for prefix in _FILE_PREFIXES:
        if folded.startswith(prefix):
            return target[len(prefix) :].strip()
    return target.strip()


def _image_from_parts(
    target: str,
    options: Sequence[str],
    source_kind: str,
    heading_path: tuple[str, ...],
    char_start: int,
    char_end: int,
) -> WikitextImage:
    layout: list[str] = []
    unknown: list[str] = []
    caption = ""
    alt = ""
    link_target = ""
    for raw_option in options:
        option = raw_option.strip()
        folded = option.casefold()
        if folded in _LAYOUT_OPTIONS or _SIZE_RE.fullmatch(folded):
            layout.append(option)
        elif folded.startswith("alt="):
            alt = option.split("=", 1)[1].strip()
        elif folded.startswith("link="):
            link_target = option.split("=", 1)[1].strip()
        elif "=" in option:
            unknown.append(option)
        elif option:
            caption = option
    return WikitextImage(
        filename=_strip_file_prefix(target),
        source_kind=source_kind,
        caption=caption,
        alt=alt,
        link_target=link_target,
        layout_options=tuple(layout),
        unknown_options=tuple(unknown),
        heading_path=heading_path,
        char_start=char_start,
        char_end=char_end,
    )


def _consume_gallery(
    rows: Sequence[tuple[str, int, int]],
    section: _SectionBuilder,
    all_images: list[WikitextImage],
    diagnostics: list[WikitextDiagnostic],
) -> None:
    for line, start, end in rows:
        stripped = line.strip()
        if not stripped:
            continue
        parts = _split_top_level(stripped, "|")
        target = parts[0].strip()
        if not _is_file_target(target):
            target = f"File:{target}"
        image = _image_from_parts(
            target,
            parts[1:],
            "gallery",
            section.heading_path,
            start,
            end,
        )
        section.images.append(image)
        all_images.append(image)
        if image.caption:
            section.blocks.append(WikitextBlock(image.caption, start, end, False))
        if image.unknown_options:
            diagnostics.append(
                WikitextDiagnostic(
                    "unknown_image_option",
                    start,
                    end,
                    section.heading_path,
                    {"count": len(image.unknown_options)},
                )
            )


def _strip_table_cell(value: str) -> str:
    cell = value.strip()
    if "|" in cell:
        before, after = cell.split("|", 1)
        if "=" in before:
            cell = after.strip()
    return cell


def _redirect_cycles(
    redirects: Mapping[int, str],
    title_to_pageid: Mapping[str, int],
) -> set[int]:
    cycles: set[int] = set()
    for origin in redirects:
        path: list[int] = []
        current = origin
        while current in redirects:
            if current in path:
                cycles.update(path[path.index(current) :])
                break
            path.append(current)
            target = redirects[current]
            current = title_to_pageid.get(target, -1)
    return cycles


def _resolve_redirect_target(
    target: str,
    redirects: Mapping[int, str],
    title_to_pageid: Mapping[str, int],
) -> int | None:
    pageid = title_to_pageid.get(target)
    visited: set[int] = set()
    while pageid in redirects:
        if pageid in visited:
            return None
        visited.add(pageid)
        pageid = title_to_pageid.get(redirects[pageid])
    return pageid


def _section_token(
    heading_path: tuple[str, ...],
    occurrences: dict[str, int],
) -> tuple[str, int]:
    if not heading_path:
        return "lead", 1
    base = hashlib.sha256("\x1f".join(heading_path).encode("utf-8")).hexdigest()[:20]
    occurrences[base] = occurrences.get(base, 0) + 1
    occurrence = occurrences[base]
    token = base if occurrence == 1 else f"{base}-occurrence-{occurrence:02d}"
    return token, occurrence


def _chunk_section(
    section: WikitextSection,
) -> list[tuple[str, int, int, bool]]:
    pieces: list[WikitextBlock] = []
    for block in section.blocks:
        if len(block.visible_text) <= 1600:
            pieces.append(block)
            continue
        start = 0
        while start < len(block.visible_text):
            end = min(start + 1600, len(block.visible_text))
            if end < len(block.visible_text):
                boundary = max(
                    block.visible_text.rfind(mark, start, end)
                    for mark in ("\n", "。", "！", "？", ". ", "! ", "? ")
                )
                if boundary > start:
                    end = boundary + 1
            pieces.append(
                WikitextBlock(
                    block.visible_text[start:end],
                    block.char_start,
                    block.char_end,
                    block.has_non_link_text,
                )
            )
            start = end
    if not pieces and (section.links or section.images):
        label = " ".join(link.label for link in section.links)
        pieces.append(
            WikitextBlock(
                label,
                section.char_start,
                section.char_end,
                False,
            )
        )
    chunks: list[tuple[str, int, int, bool]] = []
    pending: list[WikitextBlock] = []
    pending_length = 0
    for piece in pieces:
        added = len(piece.visible_text) + (2 if pending else 0)
        if pending and pending_length + added > 1200:
            chunks.append(_combine_blocks(pending))
            pending = []
            pending_length = 0
        pending.append(piece)
        pending_length += len(piece.visible_text) + (2 if len(pending) > 1 else 0)
    if pending:
        chunks.append(_combine_blocks(pending))
    return chunks


def _combine_blocks(blocks: Sequence[WikitextBlock]) -> tuple[str, int, int, bool]:
    return (
        "\n\n".join(block.visible_text for block in blocks),
        blocks[0].char_start,
        blocks[-1].char_end,
        any(block.has_non_link_text for block in blocks),
    )


def _image_binding_child(
    image: WikitextImage,
    children: Sequence[PageChildProjection],
    context_before: str = "",
    context_after: str = "",
) -> PageChildProjection:
    if image.caption:
        caption_matches = [
            child for child in children if image.caption in child.content
        ]
        if len(caption_matches) == 1:
            return caption_matches[0]
    context_matches = sorted(
        (
            (
                int(bool(_suffix_overlap(context_before, child.content)))
                + int(bool(_prefix_overlap(context_after, child.content))),
                len(_suffix_overlap(context_before, child.content))
                + len(_prefix_overlap(context_after, child.content)),
                -index,
                child,
            )
            for index, child in enumerate(children)
        ),
        key=lambda item: item[:3],
        reverse=True,
    )
    if context_matches and context_matches[0][0] > 0:
        return context_matches[0][3]
    for child in children:
        source_ref = child.source_refs[0]
        if source_ref["char_start"] <= image.char_start < source_ref["char_end"]:
            return child
    for child in children:
        if image.char_start < child.source_refs[0]["char_end"]:
            return child
    return children[-1]


def _context_for_child(
    child: PageChildProjection,
    image: WikitextImage,
    context_before: str,
    context_after: str,
) -> tuple[str, str]:
    if image.caption and image.caption in child.content:
        caption_start = child.content.find(image.caption)
        caption_end = caption_start + len(image.caption)
        return (
            child.content[:caption_start][-200:],
            child.content[caption_end:][:200],
        )
    return (
        _suffix_overlap(context_before, child.content),
        _prefix_overlap(context_after, child.content),
    )


def _suffix_overlap(value: str, content: str) -> str:
    limit = min(200, len(value), len(content))
    for length in range(limit, 0, -1):
        candidate = value[-length:]
        if candidate in content:
            return candidate
    return ""


def _prefix_overlap(value: str, content: str) -> str:
    limit = min(200, len(value), len(content))
    for length in range(limit, 0, -1):
        candidate = value[:length]
        if candidate in content:
            return candidate
    return ""


def _source_ref(
    title: str,
    pageid: int,
    revid: int,
    content_sha256: str,
    heading_path: tuple[str, ...],
    char_start: int,
    char_end: int,
) -> dict[str, Any]:
    return {
        "source_kind": "crawler_wikitext",
        "source_title": title,
        "source_row_id": f"wikitext:{pageid}:{revid}:{char_start}:{char_end}",
        "source_content_sha256": content_sha256,
        "pageid": pageid,
        "revid": revid,
        "heading_path": list(heading_path),
        "char_start": char_start,
        "char_end": char_end,
    }
