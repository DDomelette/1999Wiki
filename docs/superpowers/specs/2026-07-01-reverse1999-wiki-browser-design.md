# Reverse:1999 Wiki Browser Design

Date: 2026-07-01
Project: `1999Search`
Status: Draft for user review

## Summary

Build an independent local Wiki experience inside the existing React + Vite frontend. The Wiki will browse exported Obsidian content from `D:\Obsidian_depot\Reverse1999` without changing the existing LangChain RAG question-answering pipeline.

The first version uses a static export model:

```text
Obsidian vault
  -> existing RAG extractor
       data/processed/documents.jsonl
       Milvus vectors
       QA system

  -> new Wiki exporter
       frontend/react-app/public/wiki/manifest.json
       frontend/react-app/public/wiki/pages/*.json
       frontend/react-app/public/wiki/assets/**

React + Vite
  -> /wiki
       static manifest
       static page JSON
       static media assets
```

This keeps Wiki rendering concerns separate from RAG cleaning, chunking, retrieval, and vector storage.

## Goals

- Add a dedicated `/wiki` route to the existing React + Vite app.
- Export all eligible Obsidian pages and referenced assets into frontend static files.
- Preserve enough Markdown, frontmatter, image, and link information to build a browsable Wiki.
- Prioritize three first-class page templates: character detail, story detail, and generic Markdown.
- Keep the existing QA system isolated and unaffected.
- Leave animation integration configurable so the user can later choose ReactBits components per page area.

## Non-Goals

- Do not rebuild the existing React + Vite project.
- Do not replace the current chat or RAG screens.
- Do not use `data/raw` as the Wiki data source.
- Do not modify `data/processed/documents.jsonl`.
- Do not clear or migrate Milvus collections.
- Do not reuse `clean_markdown()` for Wiki display export.
- Do not introduce MinIO, Base64 image embedding, CDN, or a new storage service in this phase.
- Do not expose the Obsidian vault or `data/raw` directly through FastAPI.

## Confirmed Scope

The first version follows a mixed rollout:

- Export full Wiki data and assets.
- Make all exported pages basically browsable.
- Polish layout first for:
  - `character`
  - `story`
  - `markdown`
- Add `/wiki` as a new route.
- Add three entry points that all navigate to `/wiki`:
  - top navigation bar
  - side bar
  - the bottom-right CTA on the final `日历` page, with `进入WIKI` above a right arrow

## Existing System Boundaries

The current RAG path remains unchanged:

```text
scripts/extract_data.py
  -> src/extraction/obsidian_extractor.py
  -> data/processed/documents.jsonl
  -> scripts/build_index.py
  -> src/rag/vectorstore.py
  -> Milvus
  -> FastAPI QA endpoints
```

The new Wiki exporter is a separate path:

```text
scripts/export_wiki.py
  -> frontend/react-app/public/wiki/**
  -> React /wiki route
```

The exporter must only write its own output directory. It must not write `data/raw`, `data/processed`, or vectorstore state.

## Wiki Exporter

Create `1999Search/scripts/export_wiki.py`.

Responsibilities:

- Read `obsidian.vault_path` from `config/settings.yaml`.
- Traverse the 100-600 content directories:
  - `100-UTTU人物合辑`
  - `200-相从心生`
  - `300-以影像之`
  - `400-箱外世界`
  - `500-箱外阵营`
  - `600-箱中日历`
- Skip non-content areas:
  - `.obsidian`
  - `000-箱的构造/templates`
  - `000-箱的构造/script`
  - `000-箱的构造/插件`
  - Kanban pages
  - root README and vault meta pages unless explicitly included later
- Parse frontmatter when possible.
- Preserve Markdown body for display; do not use the RAG text cleaner.
- Rewrite image embeds into browser-loadable `/wiki/assets/...` URLs.
- Copy referenced assets into `frontend/react-app/public/wiki/assets`.
- Generate:
  - `frontend/react-app/public/wiki/manifest.json`
  - `frontend/react-app/public/wiki/pages/*.json`
- Clean only `frontend/react-app/public/wiki` before export.

The exporter should be idempotent: running it repeatedly creates the same output for the same source vault state.

## Manifest Format

`frontend/react-app/public/wiki/manifest.json` is the list/search/routing index.

Shape:

```json
{
  "generatedAt": "2026-07-01T00:00:00+08:00",
  "sourceVault": "D:/Obsidian_depot/Reverse1999",
  "schemaVersion": 1,
  "categories": [
    { "key": "人物", "count": 105 },
    { "key": "剧情", "count": 59 }
  ],
  "pages": [
    {
      "id": "300-以影像之/301-主线/1.0 生者与余众/此即明日｜This Is Tomorrow",
      "title": "此即明日",
      "subtitle": "This Is Tomorrow",
      "category": "剧情",
      "template": "story",
      "sourcePath": "300-以影像之/301-主线/1.0 生者与余众/此即明日｜This Is Tomorrow.md",
      "pageUrl": "/wiki/pages/<stable-page-file>.json",
      "cover": "/wiki/assets/<stable-asset-file>.png",
      "tags": ["主线"]
    }
  ],
  "warnings": []
}
```

Rules:

- `id` is the vault-relative Markdown path without `.md`.
- `pageUrl` must be stable and URL-safe.
- `title` priority:
  - `Name`
  - `Chapter`
  - `title`
  - Markdown filename without extension
- `subtitle` priority:
  - `English`
  - alias that looks like an English title
  - empty string
- `template` is one of:
  - `character`
  - `story`
  - `markdown`

## Page JSON Format

Each page is stored in `frontend/react-app/public/wiki/pages/*.json`.

Shape:

```json
{
  "id": "300-以影像之/301-主线/1.0 生者与余众/此即明日｜This Is Tomorrow",
  "title": "此即明日",
  "subtitle": "This Is Tomorrow",
  "category": "剧情",
  "template": "story",
  "sourcePath": "300-以影像之/301-主线/1.0 生者与余众/此即明日｜This Is Tomorrow.md",
  "frontmatter": {},
  "markdown": "Markdown body with /wiki/assets/... image URLs",
  "links": ["other/page/id"],
  "backlinks": ["other/page/id"],
  "assets": [
    {
      "source": "assets/此即明日｜This Is Tomorrow.assets/此即明日.png",
      "url": "/wiki/assets/<stable-asset-file>.png",
      "type": "image"
    }
  ],
  "warnings": []
}
```

## Asset Resolution

Support these source image syntaxes:

```md
![[xxx.png]]
![[path/to/xxx.png|alias]]
![alt](assets/xxx.png)
```

Resolve paths in this order:

1. If the image path is relative, resolve it from the current Markdown file directory.
2. If it is already vault-relative, resolve it from the vault root.
3. If it is only a filename, first try the current page's `assets/<page-name>.assets` directory.
4. If still unresolved, use a vault-wide filename index as fallback.
5. If unresolved after all attempts, keep a warning in page JSON and leave a visible missing-media placeholder in the rendered page.

Copied asset filenames should be stable and URL-safe. A path-derived hash is acceptable and preferred over raw Chinese/special-character browser paths.

## Frontend Route

Add a dedicated `/wiki` route inside the existing React app.

The route reads:

```text
/wiki/manifest.json
/wiki/pages/<page-file>.json
/wiki/assets/...
```

It does not call the RAG API for page content.

## Page Structure

The `/wiki` route is a Wiki workspace:

```text
/wiki
+--------------------------------------------------------------+
| WikiShell                                                    |
+-- hidden left edge trigger --+-------------+-------------+---+
| CategoryRail                  | PageIndex   | WikiReader  | PageContext
| hidden category drawer         | page list   | main reader | right info
+-------------------------------+-------------+-------------+---+
```

Relative space priority:

```text
PageContext < CategoryRail(open) = PageIndexPanel < WikiReader
```

### WikiShell

Owns route-level state:

- manifest loading state
- selected category
- search query
- selected page
- current page JSON
- load errors

It also provides a return path back to the existing app.

### CategoryRail

The category rail is normally hidden inside the left boundary. It is revealed when the cursor approaches or hovers the left screen edge.

Content:

- 人物
- 心相
- 剧情
- 世界
- 阵营
- 日历

Behavior:

- It changes the selected category.
- It displays category counts.
- It must not own page content rendering logic.
- When open, its width is close to the PageIndexPanel width.
- Opening it should avoid disruptive layout jumps in the WikiReader.

### PageIndexPanel

Always visible beside the hidden category rail.

Content:

- search input
- current category filter
- page cards
- title, subtitle, category, template
- optional thumbnail/cover after asset export is stable

The panel is narrower than the WikiReader and similar in width to the open CategoryRail.

### WikiReader

The central and largest area.

It is template-aware and must not hard-code every page into the same "cover plus body" layout.

Internal sections:

```text
PageHeader
PageMedia or Gallery
FrontmatterSummary
MarkdownRenderer
RelatedLinks
```

Different templates can reorder or resize these sections.

### PageContext

The narrow right-side support panel.

Content:

- source path
- template
- asset count
- outbound link count
- backlink count
- page outline
- related pages

It is auxiliary and should not dominate the reading experience.

## Page Templates

### Character Template

Used for pages in the `人物` category and character-like pages.

Expected emphasis:

- title and English/alias subtitle
- profile metadata from frontmatter
- main portrait or gallery when present
- rendered Markdown body
- related story, faction, or psychube links when extractable

### Story Template

Used for pages in `300-以影像之`.

Expected emphasis:

- chapter title
- English title
- era, version, launch time, serial metadata when present
- poster or cover media
- rendered Markdown story content
- related story pages and backlinks

### Generic Markdown Template

Used for all other pages.

Expected emphasis:

- title
- source context
- article-first Markdown rendering
- images and tables inline
- related links/backlinks

## Wiki Entry Points

Add three navigation entry points to the existing frontend:

```text
TopNav
  -> Wiki button/link -> /wiki

Sidebar
  -> Wiki button/link -> /wiki

Data/Calendar final section
  -> bottom-right CTA -> /wiki
```

The calendar CTA is a visual "continue to Wiki" exit:

```text
进入WIKI
   -> right arrow
```

It appears in the bottom-right of the final `日历` page. All three entry points must share the same route target.

## Animation Hooks

The user will choose ReactBits components later. The implementation must leave animation mapping configurable per area.

Animation areas:

- CategoryRail reveal/hide
- CategoryRail category item entry
- PageIndexPanel page card list entry
- PageIndexPanel card hover
- WikiReader page transition
- WikiReader image/media hover
- PageContext entry/update
- Calendar CTA arrow/label

Confirmed behavior intent:

- CategoryRail appears from the left boundary.
- Category label appears before category items.
- Category items pop in one by one after the label.
- Page cards enter upward from slightly below their resting position.
- Page cards transition from blurred to sharp during entry.
- Card hover can add slight tilt, displacement, and background glow.
- Hover states can preview or emphasize the card's related image when available.
- Main media hover uses a similar tilt/glow language.

No ReactBits component name is locked in by this spec.

## Error Handling

Exporter:

- Missing vault path: fail with a clear message.
- Unreadable Markdown: skip page and add warning to manifest.
- Frontmatter parse failure: keep body, add page warning.
- Missing asset: keep page, add page warning, render placeholder.
- Duplicate asset basename: use path-derived stable filenames.

Frontend:

- Missing manifest: show Wiki data not exported state.
- Empty manifest: show empty Wiki state.
- Missing page JSON: show page load error and keep index usable.
- Missing image: show broken-media placeholder, not a blank layout.
- Search with no results: show no-results state.

## Testing Strategy

Exporter tests:

- exports manifest and page JSON from a small fixture vault
- rewrites Markdown image syntax
- rewrites Obsidian image embed syntax
- copies referenced image assets
- handles unresolved media with warnings
- does not write `data/processed`
- does not import or call `clean_markdown()`

Frontend tests:

- `/wiki` loads manifest and renders page list
- selecting a page fetches page JSON
- category filter changes visible pages
- search filters visible pages
- missing manifest state is user-readable
- page templates select the expected renderer
- three Wiki entry points target `/wiki`

Manual verification:

- run exporter against the real Reverse1999 vault
- confirm `/wiki/manifest.json` exists
- confirm at least one character, story, and generic Markdown page renders
- confirm referenced images load from `/wiki/assets/...`
- confirm existing chat/RAG flows still load

## Git Hygiene

Generated Wiki output should not be committed by default.

Recommended ignore rules:

```gitignore
frontend/react-app/public/wiki/**
!frontend/react-app/public/wiki/.gitkeep
!frontend/react-app/public/wiki/manifest.sample.json
```

If a frontend schema fixture is needed, commit a small sample or schema file, not the full asset export.

The `.superpowers/` brainstorm directory is local-only and should not be committed.

## Acceptance Criteria

- A spec-approved implementation can add `/wiki` without changing RAG extractor semantics.
- Running the Wiki exporter creates static Wiki files under `frontend/react-app/public/wiki`.
- The existing QA system continues to use `documents.jsonl` and Milvus.
- The `/wiki` route can browse exported pages and display copied images.
- Category rail, page index, reader, and page context have clear ownership.
- The left category rail is hidden by default and revealed from the left edge.
- Layout priority follows: right info < open category rail = page index < reader.
- The three Wiki entry points all navigate to `/wiki`.
- Animation integration points are identified but not coupled to a specific ReactBits component yet.
