# 灰机媒体-文本语义对齐标注设计

日期：2026-07-09  
状态：迭代版规格，用于指导 Wiki 与 RAG 共用的媒体语义标注工作。  
适用范围：灰机爬虫数据、处理产物、MinIO 已有媒体、未来增量媒体的分类与文本绑定设计。

## 1. 背景与目标

当前项目已经具备灰机爬虫数据、RAG 处理产物、MinIO 媒体对象和 Wiki 页面展示链路，但媒体资源的业务语义仍不够稳定。单靠文件名只能初步判断“这是什么图”，不能稳定回答“它属于哪个角色、哪个皮肤、哪个技能、哪个活动、旁边应该显示哪段描述”。

本规格把原先的“媒体视觉分类”升级为“媒体-文本语义对齐标注”：

- 视觉标注回答：图片是什么类型。
- 文本标注回答：图片与哪些页面文本、模板字段、描述、章节、活动规则关联。
- 连接标注回答：图片、实体、皮肤、技能、活动、卡池、来源页之间如何绑定。

最终产物应服务两个方向：

- Wiki：决定图片在哪个模块展示、使用哪个模板、旁边显示什么文字、缺失时如何 fallback。
- RAG：为答案引用媒体、来源跳转、实体解析、后续多模态增强提供稳定语义层。

## 2. 总体架构

标注系统采用“源数据共用，构建层分流，展示层解耦”的原则。

```text
灰机爬虫原始数据
  pages.jsonl / wikitext.jsonl / data_pages.jsonl / resources_manifest.jsonl / assets/files
        |
        v
媒体-文本语义对齐标注层
  visual_role + text_binding + entity_binding + confidence + review_status
        |
        +--> Wiki 派生 manifest / MySQL 展示表
        |
        +--> RAG media metadata / source 跳转 / 多模态引用增强
```

标注层不直接替代 RAG artifacts，也不直接扫描 MinIO 反推业务关系。MinIO 是对象池；业务索引以爬虫源数据、处理产物和人工标注结果为准。

## 3. 数据来源模块

### 3.1 模块职责

定义标注时允许参考的数据来源、优先级和只读边界。

### 3.2 P0 当前必须满足

`SRC-P0-01`: 标注必须同时参考人工确认、处理产物和爬虫源数据，不能只看图片文件名。  
优先级从高到低为：用户人工解释、爬虫页面文本、RAG 处理产物、资源文件名、视觉猜测。

`SRC-P0-02`: 当前可用的主要数据源为：

- `data/huiji/res1999/pages.jsonl`
- `data/huiji/res1999/wikitext.jsonl`
- `data/huiji/res1999/data_pages.jsonl`
- `data/huiji/res1999/resources_manifest.jsonl`
- `data/processed/huiji/dev/media_assets.jsonl`
- `data/processed/huiji/dev/parent_blocks.jsonl`
- `data/processed/huiji/dev/child_blocks.jsonl`
- MinIO 中 `media_assets.jsonl` 已引用的 HTTP URL

`SRC-P0-03`: 标注过程只读这些数据源，不修改 Milvus、MinIO、RAG artifacts、向量库或现有问答链路。

`SRC-P0-04`: 不在 MinIO 中、但存在于爬虫资源层或页面文本中的媒体，也可以按同一规范标注。未来是否纳入 MinIO，由后续构建/同步计划决定。

### 3.3 P1 可部分支持

`SRC-P1-01`: 建立资源反查索引，将文件名、sha1、source_url、descriptionurl、页面标题、wikitext 引用位置聚合到同一记录。

`SRC-P1-02`: 对同一视觉资源的 `webp/png/jpg` 多格式版本建立 `visual_asset_key`，区分轻量展示图和放大图。

### 3.4 P2 未来演进

`SRC-P2-01`: 支持增量爬虫数据进入标注队列，并在 RAG/Wiki 共同审核后纳入统一媒体语义层。

### 3.5 关键契约与限制

- 爬虫源数据是解释媒体语义的首要机器来源。
- MinIO 只作为媒体对象存储参考，不作为业务分类来源。
- RAG 当前可继续稳定运行，标注工作优先级高于 RAG 迭代，但不得破坏 RAG 已有链路。

## 4. 视觉分类模块

### 4.1 模块职责

定义媒体图片本身的业务类型，输出 `visual_role` 和必要的子字段。

### 4.2 P0 当前必须满足

`VIS-P0-01`: 标注必须区分角色核心视觉类型，至少包括：

| visual_role | 中文名 | 典型文件名 | 说明 |
| --- | --- | --- | --- |
| `live2d_static` | Live2D 静态图 | `L2d_static-300301_hujisheng.webp` | 角色 Live2D 展示图。 |
| `portrait` | 立绘 | `Portrait-300301.webp` | 角色皮肤立绘，通常可作为主视觉。 |
| `chibi` | 小人物形象 | `Spine_static-300301_hujisheng.webp` | 战斗中的小人物形态。 |
| `udimo` | 尤提姆 / Udimo | `Spine_static-300301_hujisheng_s.webp` | 待命形态，小人物的变体。 |
| `portrait_avatar_small` | 立绘小尺寸头像 | `Headicon_small-300301.png` | 由立绘/半身视觉裁出的头像。 |
| `chibi_avatar_small` | 小人物小尺寸头像 | `HeadIconSmall-*` | 小人物形态的头像，需要继续抽样确认。 |
| `enemy_chibi_avatar_small` | 敌方小人物小尺寸头像 | `MonsterHeadIcon-300201.png` | 实时对战中的敌方单位头像。 |
| `live2d_avatar_large` | Live2D 大头像 | `Headicon_large-300301.png` | Live2D 视觉裁出的角色大头像。 |
| `portrait_avatar_large` | 立绘大头像 | `Headicon_large-300302.png` | 立绘/皮肤视觉裁出的角色大头像。 |

`VIS-P0-02`: 标注必须区分技能和战斗卡资源。`Skill-*` 文件名前缀不等于角色技能，可能包含角色技能卡、活动机制牌、场地效果牌、通用功能牌。至少记录 `skill_slot`、`skill_name`、`card_type`、星级/阶段、机制标签、`provider_type` 和是否归属角色。

`VIS-P0-03`: 标注必须区分活动、卡池和标题素材，至少包括：

| visual_role | 中文名 | 典型文件名 | 说明 |
| --- | --- | --- | --- |
| `character_story_event_banner` | 角色剧情活动 Banner | `Banner_荣耀废墟与隐喻指南.png` | 虚构集等个人剧情活动横幅。 |
| `summon_banner` | 征集 / 卡池 Banner | `Banner_征集·火花雀儿.jpg` | 抽卡卡池横幅。 |
| `summon_title_logo` | 征集 / 卡池标题素材 | `SummonPool-火花雀儿.png` | 从卡池视觉中拆出的标题/Logo。 |
| `event_versatile_card_art` | 活动专属功能牌卡面 | `Skill-103001.png` | 活动或关卡机制提供的 Versatile 卡，不归属角色。 |
| `generic_versatile_card_art` | 通用功能牌卡面 | `Skill-103004.png` | 通用场地机制功能牌，可按正向、负向、中性、治疗等倾向细分。 |
| `field_generic_card_art` | 场地牌 / 场地效果通用卡面 | `Skill-2305.png` | 绝大多数情况下由场地效果提供的通用卡面，可作为手牌或场地机制牌，不归属角色或敌方单位。 |
| `revelation_effect_display_card_art` | 启示效果展示卡面 | `Skill-760081.png` | 通常由系统控制，满足层数或回合条件后自动发动，不需要玩家打出。 |
| `boss_card_art` | Boss 卡牌 | `Skill-760061.png` | Boss 专属或 Boss 机制卡牌。部分 Boss 可作为玩家队友“背后灵”出现；多形态 Boss 需要记录形态。 |
| `bloodtithe_team_card_art` | 薪血队机制卡面 | `Skill-760100.png` | 与薪血队机制相关的卡面，可关联消耗薪血、回复、薪血层数等效果。 |
| `bloodtithe_status_display_art` | 薪血状态展示图 | 待补充 | 用于展示当前薪血层数等状态，常与薪血队角色关联。 |
| `enemy_generic_card_art` | 敌方通用技能卡面 | `Skill-1101.png` | 敌方单位通用技能视觉。同一卡面可能对应不同名称和效果，最终类型看页面描述。 |

`VIS-P0-04`: 不能把所有“小尺寸头像”合并为同一类。必须通过横向对比区分立绘头像、小人物头像、敌方小人物头像。

### 4.3 P1 可部分支持

`VIS-P1-01`: 扩展识别 Buff、Debuff、Counter、Channel、Adaptive、机制图标、成就卡牌、物品、心相、藏品、房间、Rogue、UTTU 等主要命名族。

`VIS-P1-02`: 对角色稀有度展示建立规则。`Headicon_large-*` 底部光影可辅助展示：橙色为六星、金黄色为五星、紫色为四星、蓝色为三星、绿色为一星。但稀有度应优先来自结构化字段。

### 4.4 P2 未来演进

`VIS-P2-01`: 使用自动分类模型或脚本对长尾资源先粗分，再由人工只复核未知、高频、冲突样本。

### 4.5 关键契约与限制

- 文件名前缀是线索，不是最终语义。
- `Portrait`、`Spine`、`L2d` 的编号不保证一一对应，必须通过 `skin_key`、页面文本、人工标注和来源页合并。

## 5. 文本语义绑定模块

### 5.1 模块职责

把图片与页面文本、模板字段、描述、章节、规则、活动信息绑定，避免图片只成为孤立素材。

### 5.2 P0 当前必须满足

`TXT-P0-01`: 标注任务必须纳入与媒体直接相关的文本，而不是全文人工标注。优先标注：

- 图片所在页面标题
- 图片链接附近的标题、caption、表格行、模板字段
- 角色、皮肤、尤提姆、技能、活动、卡池描述
- 章节名、小游戏规则、成就说明
- 文件页标题、source_url、descriptionurl

`TXT-P0-02`: 皮肤描述绑定到 `character_id + skin_key`，可被 `portrait / live2d_static / chibi` 共用。

`TXT-P0-03`: 尤提姆描述绑定到 `character_id + skin_key + visual_role=udimo`。

`TXT-P0-04`: 技能描述绑定到 `character_id + skill_slot + skill_name`，并记录卡牌类型和机制标签。

`TXT-P0-04A`: 非角色功能牌描述不得绑定到 `character_id`。Versatile 功能牌应绑定到 `event_name / stage_key / mechanic_name / provider_type`，并记录 `card_type=Versatile`。

`TXT-P0-04B`: 敌方通用技能卡面不得直接绑定为友方角色技能。该类资源应优先绑定 `enemy_id / encounter_id / stage_key / skill_name / effect_text`；同一卡面允许对应多个技能名和效果。

`TXT-P0-04C`: 敌方通用技能卡面可记录 `enemy_visual_family`，用于描述视觉/阵营风格，例如魔精类、重塑之手类、军队系、帮派类、第一防线学校在校生。该字段不替代具体敌人、关卡和技能效果。

`TXT-P0-04D`: 若页面描述明确敌方组织，应另记 `enemy_org`，例如岩城帮会、启明会、鬓影姐妹会、第一防线学校在校生。`enemy_visual_family` 是视觉粗分类，`enemy_org` 是文本确认的组织归属，二者不能混用。

`TXT-P0-04E`: 敌方通用卡面的细分不是强制字段。若视觉或组织边界不稳定，应保留 `visual_role=enemy_generic_card_art`，并依赖 Markdown、网页链接、关卡设定和技能描述确认具体含义。后期敌方卡面适用边界可能变模糊，不能只靠视觉强行细分。

`TXT-P0-04F`: 场地牌 / 场地效果通用卡面应记录 `visual_role=field_generic_card_art`，优先绑定 `stage_key / field_effect_id / mechanic_name / provider_type=field_effect / effect_text`。该类资源通常由场地效果提供，不应绑定到 `character_id` 或 `enemy_id`，除非页面文本明确说明由某个实体生成。

`TXT-P0-04G`: 启示效果展示卡面应记录 `visual_role=revelation_effect_display_card_art`，优先绑定 `revelation_id / mechanic_name / auto_trigger_condition / stack_count / effect_text / source_page`。这类资源通常由系统控制，攒够层数或每回合结尾自动发动，不属于玩家需要打出的手牌。

`TXT-P0-04H`: 薪血队机制卡面应记录 `visual_role=bloodtithe_team_card_art` 或 `bloodtithe_status_display_art`，优先绑定 `mechanic_name=薪血 / team_archetype=薪血队 / related_character_ids[] / stack_count / consume_rule / effect_text / source_page`。如果是爱心形状态展示图，应重点记录其用于展示当前薪血层数，而不是作为可打出的手牌。

`TXT-P0-04I`: Boss 卡牌应记录 `visual_role=boss_card_art`，优先绑定 `boss_id / boss_name / boss_form / encounter_id / stage_key / skill_name / effect_text / source_page`。若该 Boss 可作为玩家队友“背后灵”出现，应记录 `can_appear_as_back_spirit=true` 及对应上下文。多形态 Boss 的不同卡牌不能仅凭相似图案合并。

`TXT-P0-05`: 活动 Banner 绑定到 `event_type + event_name`，卡池 Banner 绑定到 `pool_name + pool_type + up_characters`。

### 5.3 P1 可部分支持

`TXT-P1-01`: 对 Markdown/wikitext 中的文件链接建立“引用位置”字段，记录图片来自哪个标题、表格、模板或段落。

`TXT-P1-02`: 对同一图片的多处引用建立 `source_text_refs[]`，允许 Wiki/RAG 根据上下文选择最合适的解释文本。

### 5.4 P2 未来演进

`TXT-P2-01`: 建立媒体语义搜索能力，让 RAG 可按“槲寄生洞悉皮肤立绘”“薪血机制图标”等自然语言查找媒体。

### 5.5 关键契约与限制

- 文本纳入范围只限媒体绑定相关文本，不进行全文知识标注。
- 文本绑定结果进入 RAG 前必须经过审核，避免污染检索与回答链路。

## 6. 实体连接模块

### 6.1 模块职责

定义标注输出中的实体关系字段，让 Wiki 与 RAG 能共享同一语义连接。

### 6.2 P0 当前必须满足

`LINK-P0-01`: 每条标注记录应尽量包含以下字段：

```text
filename
normalized_name
source_family
media_id
sha1
object_key
url
source_url
descriptionurl
visual_asset_key
visual_role
entity_type
entity_id
entity_name
character_id
character_name
skin_key
skin_name_cn
skin_name_en
skin_stage
skill_slot
skill_name
card_type
enemy_visual_family
enemy_org
event_type
event_name
pool_name
pool_type
up_characters
description_role
source_text
source_text_ref
confidence
review_status
notes
```

`LINK-P0-02`: 同一视觉资源的不同格式不能当成不同业务图。必须用 `visual_asset_key` 聚合，保留格式、尺寸和用途差异。

`LINK-P0-03`: 人工标注、爬虫文本、文件名推断之间存在冲突时，人工标注优先，但必须记录冲突和置信度。

### 6.3 P1 可部分支持

`LINK-P1-01`: 为 Wiki 生成页面级媒体分组，例如 `hero`, `gallery`, `skills`, `skins`, `udimo`, `event_banner`, `summon_banner`。

`LINK-P1-02`: 为 RAG 生成轻量媒体索引，允许答案根据 `entity_id/source_id/title` 找到相关 Wiki 媒体。

### 6.4 P2 未来演进

`LINK-P2-01`: 支持跨实体共享机制图标、队伍机制素材、活动复用素材等多对多关系。

### 6.5 关键契约与限制

- 连接层是派生语义层，不直接修改原始爬虫数据。
- 是否写回 MySQL、RAG 派生 manifest 或 `media_assets` 增强表，由后续 plan 和 RAG 审核决定。

## 7. 标注流程模块

### 7.1 模块职责

定义人工标注如何分批进行、如何记录结论、如何控制质量。

### 7.2 P0 当前必须满足

`FLOW-P0-01`: 标注按批次进行。每批展示 5 张相近或容易混淆的图片，方便横向对比。

`FLOW-P0-02`: 每批必须记录：

- 样本文件名
- 显示路径或 URL
- 用户给出的业务解释
- 推断出的 `visual_role`
- 相关文本字段或待查文本来源
- 命名规则
- 例外与疑点

`FLOW-P0-03`: 每批结束后应把阶段性成果写入独立标注日志，避免对话压缩导致结论丢失。稳定规则再回写本规格；样本级明细不直接堆入 specs。

`FLOW-P0-04`: 标注结果进入构建层前，必须生成可交给 RAG 链路审核的报告。

`FLOW-P0-05`: 当前标注日志为 `docs/superpowers/annotations/2026-07-09-huiji-media-semantic-annotation-log.md`。后续每轮标注优先追加到该文件。

`FLOW-P0-06`: 每轮提问前先给出模型自主识图预判，用户回答后记录 `model_guess -> user_label -> correction`，以便暴露细节误判并提升后续自动分类规则。

### 7.3 P1 可部分支持

`FLOW-P1-01`: 自动从 `resources_manifest.jsonl`、`media_assets.jsonl`、`wikitext.jsonl` 抽取候选样本，按命名族和引用上下文分组。

`FLOW-P1-02`: 对每个命名族抽取代表样本、边界样本和冲突样本，而不是随机抽样。

### 7.4 P2 未来演进

`FLOW-P2-01`: 建立审核界面或轻量标注 UI，支持图文并排、字段编辑、冲突提示和导出。

### 7.5 关键契约与限制

- 当前阶段不写数据库、不改向量库、不上传/删除 MinIO。
- 可以参考 MinIO 已有资源，但未进入 MinIO 的资源也可按同规范设计。

## 8. 已确认样例附录

### 8.1 角色与皮肤视觉

| 文件名 | visual_role | 已确认含义 |
| --- | --- | --- |
| `L2d_static-300301_hujisheng.webp` | `live2d_static` | 槲寄生原皮 Live2D 图片。 |
| `L2d_static-300901_sufubi_p.webp` | `live2d_static` | 苏芙比 Sotheby 的 Live2D 图片；`p` 后缀含义待定，只记录为 `variant=p`。 |
| `Portrait-300301.webp` | `portrait` | 槲寄生原皮立绘。 |
| `Portrait-300302.webp` | `portrait` | 槲寄生洞悉皮肤立绘，皮肤名为“熟识橡树之人 / The Druid”。 |
| `Spine_static-300301_hujisheng.webp` | `chibi` | 槲寄生原皮小人物形象。 |
| `Spine_static-300303_hujisheng.webp` | `chibi` | 槲寄生洞悉后皮肤“熟识橡树之人 / The Druid”的小人物形象。 |
| `Spine_static-300301_hujisheng_s.webp` | `udimo` | 槲寄生原皮尤提姆形象。 |
| `Spine_static-300305_hjs_s.webp` | `udimo` | 槲寄生衣着“闹蛾儿 / Lady With Nao'E”的尤提姆形象。 |

已确认文本：

- 槲寄生“熟识橡树之人 / The Druid”：`她回到橡木树梢，像是回到母亲的怀抱。`
- 槲寄生原皮尤提姆描述：`猫类尤提姆，常见。通体漆黑，毛发顺滑，弯月夜中常散发出橡木香气。独居动物，社交倾向弱，攻击性弱，性格柔和，喜好植被，对外界保有好奇心。`

### 8.2 技能卡面

| 文件名 | visual_role | 已确认含义 |
| --- | --- | --- |
| `Skill-30030111.webp` | `skill_icon` | 槲寄生一技能“风入林”，Attack 攻击卡。 |
| `Skill-30030121.webp` | `skill_icon` | 槲寄生二技能“露渐白”，Attack 攻击卡。 |
| `Skill-30030131.webp` | `skill_icon` | 槲寄生大招“林间，静默将至”。 |
| `Skill-103001.png` | `event_versatile_card_art` | 活动“行至摩卢旁卡”的群星之力功能牌“日蚀”，属于场地效果，不归属角色。 |
| `Skill-103002.png` | `event_versatile_card_art` | 活动“行至摩卢旁卡”的群星之力功能牌“月蚀”，属于场地效果，不归属角色。 |
| `Skill-103003.png` | `event_versatile_card_art` | 活动“行至摩卢旁卡”的群星之力功能牌“一次完满”，属于场地效果，不归属角色。 |
| `Skill-103004.png` | `generic_versatile_card_art` | 通用 Versatile 功能牌，通常代表正向功能。 |
| `Skill-103005.png` | `generic_versatile_card_art` | 通用 Versatile 功能牌，通常代表负面功能。 |
| `Skill-1101.png` | `enemy_generic_card_art` | 敌方角色通用技能卡面。同一视觉可能有不同名称/效果。 |
| `Skill-1102.png` | `enemy_generic_card_art` | 敌方角色通用技能卡面。同一视觉可能有不同名称/效果。 |
| `Skill-1103.png` | `enemy_generic_card_art` | 敌方角色通用技能卡面。同一视觉可能有不同名称/效果。 |
| `Skill-1104.png` | `enemy_generic_card_art` | 敌方角色通用技能卡面。同一视觉可能有不同名称/效果。 |
| `Skill-1201.png` | `enemy_generic_card_art` | 敌方角色通用技能卡面。同一视觉可能有不同名称/效果。 |

技能卡面需要记录星级、卡牌类型、技能槽位和机制标签。部分角色可能因洞悉、皮肤或核心机制变化产生不同卡面。`Skill-*` 命名族还可能包含 Versatile 功能牌和敌方通用卡面；这类卡不能直接绑定到友方角色技能，必须结合页面效果描述判断。

### 8.3 活动与卡池

| 文件名 | visual_role | 已确认含义 |
| --- | --- | --- |
| `Banner_荣耀废墟与隐喻指南.png` | `character_story_event_banner` | 虚构集《荣耀废墟与隐喻指南》的角色剧情活动 Banner。 |
| `Banner_征集·火花雀儿.jpg` | `summon_banner` | 征集“火花雀儿”的卡池 Banner。UP 角色：六星可燃点、五星和平乌鲁、五星帕米埃。规则类型：限时角色征集。 |
| `SummonPool-火花雀儿.png` | `summon_title_logo` | “火花雀儿”卡池标题素材，用于不同尺寸或不同布局的复用。 |

### 8.4 头像类

| 文件名 | visual_role | 已确认含义 |
| --- | --- | --- |
| `Headicon_small-300301.png` | `portrait_avatar_small` | 槲寄生立绘小尺寸头像，是从角色立绘/半身视觉中裁出的头像。 |
| `HeadIconSmall-*` | `portrait_avatar_small` / 待细分 | 该命名族不能只按前缀判断。已发现维尔汀立绘小头像与摘帽形态头像，后续需继续抽样拆分。 |
| `HeadIconSmall-300101.png` | `portrait_avatar_small` | 维尔汀的立绘小头像。维尔汀是承载玩家视角的主角。 |
| `HeadIconSmall-300105.png` | `portrait_avatar_small` | 维尔汀的立绘小头像，但为摘下帽子的形态。 |
| `Headicon_large-300301.png` | `live2d_avatar_large` | 槲寄生的 Live2D 大头像。 |
| `Headicon_large-300301.webp` | `live2d_avatar_large` | 槲寄生的 Live2D 大头像，与 `Headicon_large-300301.png` 是同一视觉资源的不同格式。 |
| `Headicon_large-300302.png` | `portrait_avatar_large` | 槲寄生洞悉皮肤“熟识橡树之人 / The Druid”的立绘大头像。 |
| `MonsterHeadIcon-300201.png` | `enemy_chibi_avatar_small` | 敌对角色的小人物形态小尺寸头像。部分敌方形象可能与友方相似，因为设定上可能是友方的潜意识镜像。 |
| `MonsterHeadIcon-300301.png` | `chibi_avatar_small` | 槲寄生的小人物小头像。说明 `MonsterHeadIcon-*` 可能复用友方小人物视觉，实际语义需结合上下文判断。 |

## 9. 与旧方案的关系

本规格替代原先“只做图片视觉分类”的草案。保留已确认分类和样例，但扩展为图文对齐、实体连接、批次标注和 RAG/Wiki 共享语义层设计。

本规格不替代 Wiki 页面设计、RAG 构建设计或 MinIO 迁移计划。后续如果要写入 MySQL、生成 manifest、补充 `media_assets` 派生字段或上传增量媒体，需要另写 plan，并以本规格中的 P0 条目作为验收来源。

## 10. 自检

- 已按模块组织，并在模块内划分 P0/P1/P2。
- 已提供稳定编号，便于后续 plan 引用。
- 已明确当前不修改 RAG、Milvus、MinIO、MySQL。
- 已明确文字纳入范围是媒体绑定相关文本，不是全文人工知识标注。
- 已保留第一批和第二批已确认结论。
- 未使用 `TBD` 或 `TODO` 作为未决需求占位。
