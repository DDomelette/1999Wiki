# Wiki / RAG Shared Contract Record

日期：2026-07-08
状态：RAG 共享契约已确认

## GATE-P0 确认

- [x] `GATE-P0-01`: MinIO bucket、object prefix、object key 和 HTTP URL 规则稳定。
- [x] `GATE-P0-02`: processed artifacts build_version 与 `media_assets.jsonl` 字段契约稳定。
- [x] `GATE-P0-03`: Milvus 当前 collection 已确认；Wiki 不读取 Milvus。
- [x] `GATE-P0-04`: Wiki 可只读消费媒体 URL 和 source/entity 字段，不影响问答链路。
- [x] `GATE-P0-05`: Wiki plan 获准基于已确认共享契约进入代码落地。

## RAG 确认内容

### MinIO

- bucket: `reverse1999-assets`
- public_base_url: `http://127.0.0.1:9002`
- object_prefix: `reverse1999`
- url_rule: `http://127.0.0.1:9002/reverse1999-assets/reverse1999/<asset_type>/<sha-prefix>/<sha>.<ext>`

### Processed Artifacts

- build_version: `dev`
- project-relative path: `data/processed/huiji/dev`
- required_files: `parent_blocks.jsonl`, `child_blocks.jsonl`, `media_assets.jsonl`
- parent_count: `8246`
- child_count: `16010`
- media_count: `15758`
- media index source of truth: `data/processed/huiji/dev/media_assets.jsonl`

### Milvus

- active_collection: `text_child_bge_m3_v3`
- wiki_access: `none`

### Media Display Policy

- default visible: `image`, `portrait`, `skill`
- gated visible: `voice` only in folded voice panel, dedicated tab, or explicit voice entry
- gated visible: `video` only in video panel, dedicated tab, or explicit video entry
- ignored: MinIO objects that are not referenced by `media_assets.jsonl`

### API Payload Whitelist

- allowed media fields: `media_id`, `asset_id`, `asset_type`, `mime`, `url`, `title`, `alt`, `role`, `attach_policy`, `child_id`, `parent_id`, `panel_group`, `sort_order`, `duration_ms`
- forbidden media field: `local_relpath`

## Wiki Allowed Actions

- read MySQL wiki tables through repository/API
- read API-safe HTTP media URL
- read `data/processed/huiji/dev/parent_blocks.jsonl`
- read `data/processed/huiji/dev/child_blocks.jsonl`
- read `data/processed/huiji/dev/media_assets.jsonl`
- render `/wiki`
- run read-only verification

## Wiki Forbidden Actions

- rebuild Milvus
- upload/delete/migrate MinIO object
- overwrite Wiki MySQL tables
- rerun Wiki builder
- scan MinIO directly to infer page resources
- modify RAG retrieval/vectorization/chat output
