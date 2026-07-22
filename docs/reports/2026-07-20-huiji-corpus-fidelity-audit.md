# Huiji Corpus Fidelity Audit

日期：2026-07-20  
状态：通过，存在候选 builder 必须修正的 schema/元数据问题  
执行边界：只读 crawler raw、active artifacts、BM25、Milvus、MySQL 与 MinIO；未修改 active 数据、数据库、对象存储或向量集合

## 1. 结论

当前没有发现语料大面积丢失，也没有发现 active RAG、Wiki 投影、MinIO 或 Milvus 的链路漂移。现有语料可以作为新 builder 的保真权威基线，但不能直接照搬其两个已知建模问题：

1. character data type-2/type-3 当前分别落入 `culture`/`item`，语义上应迁移为 `collection`/`culture_dossier`。
2. 旧媒体 schema 将资源身份兼作绑定身份，导致同一 `media_id` 合法对应多条 owner/child/event 绑定；候选必须改为 `resource_id + binding_id`，并完整保留每条关系。

MySQL 的 snapshot 元数据仍为 `legacy/dev`，但页面的 `source_title`、`sourceRefs` 和 crawler projection 字段均指向 `Data:*` crawler records，未发现 Obsidian 来源。该标志反映当前缺少 active build pointer，不代表正文来自 Obsidian。

## 2. 全量对账结果

### 2.1 Crawler raw inventory

| 文件 | 行数 | SHA-256 |
|---|---:|---|
| `data_pages.jsonl` | 72,848 | `eb82b82e34300ee5d8beb27b13311fe530c59faeba3ae7883876b74b0eab9092` |
| `pages.jsonl` | 134,836 | `98f24e6a674257cc5465c865cab60e0d8174104e8c14f9a4a362c9b349dd4b6b` |
| `resources_manifest.jsonl` | 61,087 | `20dfc072c2099f356d6a2b4b2572691054919b83dc9cbcc058a237109d373aa6` |
| `wikitext.jsonl` | 79,072 | `7767c589217dcde17d7a0fca3e8f6dae45e8adb46c3a6768cb81cad2493aa721` |

`data_pages.jsonl` 中有 1 条 crawler 自身标记为 invalid JSON 的记录，但它未被 active source refs 引用。候选 builder 必须将此类记录写入 excluded evidence，不能静默跳过，也不能让无关坏行删除其他有效语料。

### 2.2 Active 与外部投影

| 检查面 | 当前观测 | 结果 |
|---|---:|---|
| Parent artifacts | 8,246 | ID 唯一，结构闭环 |
| Child artifacts | 16,010 | ID 唯一，无空正文/检索文本 |
| Media binding rows | 15,758 | 全部 child/parent 可解析，本地文件与 URL 有效 |
| Explicit exclusions | 10 | 5 条缺 entity ID，5 条 placeholder name；均未进入 MySQL |
| Source references | 24,798 | 全部为 `data_page`，无 Obsidian 引用 |
| Unique crawler source titles | 7,456 | raw title 与 content SHA 全部匹配 |
| Child BM25 | 16,010 | 与 child artifact 逐行同序、完整 payload 一致 |
| Media BM25 | 15,758 | 与 media binding artifact 逐行同序、完整 payload 一致 |
| MySQL pages | 7,456 | 与当前 crawler Wiki 投影多重集完全一致 |
| MySQL media links | 17,527 | 与当前 crawler Wiki 投影多重集完全一致 |
| Active Milvus | 16,010 | runtime provenance verifier 通过 |
| `reverse1999-assets` | 17,863 objects | 相对上一份全哈希 inventory 无 key/size/ETag 漂移 |
| `a-bucket` | 192 objects | 相对上一份全哈希 inventory 无漂移 |

当前 7,456 个实体页面按类型分为：character 132、story 6,413、item 906、psychube 5。active child 的 section 分布为：profile 7,456、dossier 134、culture 813、item 396、skill 407、voice 6,804。其中 `culture` 813 与 `item` 396 是必须通过 raw 证据迁移的旧语义名称，不得按名称直接丢弃。

旧 RAG 媒体绑定按 `asset_type` 分为 image 597、portrait 781、skill 399、voice 13,981。MySQL 额外保存的 crawler 语义媒体行按 `media_role` 分为 collection_item 810、roster_avatar 132、skin_background 137、stage_live2d 280、stage_portrait 388、udimo 22。

MySQL 媒体由 15,758 条旧 RAG 绑定和 crawler 语义媒体增量组成。crawler-only dry-run 本次生成 1,763 个唯一媒体 operation，全部已存在于 MinIO，missing 与 conflict 均为零；`wiki-supplement` 私有前缀和 supplement tables 均为空。

## 3. 媒体重复项定性

15,758 条旧媒体行包含 15,383 个唯一 `media_id`，共有 375 个重复资源 ID group，并产生 375 条超出唯一资源数的绑定行：

- 368 组位于同一实体内，但绑定到不同 child/event。
- 7 组跨实体共享相同内容资源。
- 375 组的绑定 tuple 均互不相同，没有可按资源 ID 直接删除的重复关系；这不等于每条旧绑定都已证明语义正确，候选仍须用 EVB/owner 证据决定 `preserved_exact` 或 `corrected_semantics`。

因此旧数据不是“多了 375 个无效文件”，而是 schema 不能同时表达资源身份和关系身份。候选 builder 必须保留资源复用，同时为每条关系生成独立 `binding_id`；按 SHA、object key 或旧 `media_id` 去重都会造成真实绑定丢失。

## 4. MinIO 范围

当前 active RAG 引用 15,383 个唯一 object key，Wiki 引用 16,481 个唯一 object key，全部存在且声明 SHA-1 与上一份全 SHA-1/SHA-256 inventory 一致。

`reverse1999-assets` 中另有 1,382 个不在当前 Wiki consumer set 的对象。本次只将其记录为 remote residual/orphan diagnostic，不把它们视为语料缺失，也不生成删除计划。它们属于独立 P2 清理范围。

## 5. 保真策略

新 builder 不以“总数接近”作为验收，而是要求 active 的每个 parent、child、media binding、excluded 和 BM25 record 恰好进入一种分类：

```text
preserved_exact
preserved_rekeyed
corrected_semantics
removed_with_source_reason
```

未受影响内容必须保持规范化业务字段、文本、source refs、owner/section 和相对顺序等值。允许变化仅限有 raw 证据的 section 修正、Udimo/语义媒体新增、已解释的 EVB 绑定纠正、资源/绑定双 ID 迁移以及 source inventory 本身的显式变化。

验收硬指标为：

```text
unexplained_missing = 0
unexplained_binding_loss = 0
BM25 sequence mismatch = 0
source hash mismatch = 0
MinIO declared hash mismatch = 0
```

当前快照数字只存在于 evidence 和本报告中；实现与测试从 hash-pinned 输入动态计算 expected 集合，不写死角色、台词、语言、collection、Udimo 或当前总数。

## 6. 证据

- `eval/huiji_corpus_fidelity/20260720T073917Z/corpus-preservation-baseline.v2.json`  
  SHA-256: `8df26d9a6cd1014c82d1fdd1fa858f1b9411cb4b365101b0a12020d608db10aa`
- `eval/huiji_corpus_fidelity/20260720T073917Z/runtime-current-v2/runtime.v1.json`  
  SHA-256: `c67cc94a6be8669a47dfeb7cd5dc6042b10f80986fd9dff41364ebdf9cc142c6`
- `eval/huiji_corpus_fidelity/20260720T073917Z/wiki-dry-run-current-v2/preflight.json`  
  SHA-256: `68cb37bdfa3fb1c18dab4d7ed8ad65d91319de8b8251d361c314dda72ff96d9f`
- `eval/huiji_source_cleanup/20260719T215123Z-huiji-p2/p2/verification/post-inventory.v1.json`  
  SHA-256: `3013b6893ab19b2a378c6622270a5956db090bacc5779b35cd7e51a233c875a8`

早期 `active-corpus-fidelity.v1.json` 继续保留用于证据链追踪，但其 shell 编码导致的 mojibake 误报、duplicate media ID map 折叠导致的 BM25 误报，以及 malformed Wiki map 统计均已在 v2 中更正，不再作为验收依据。
