# 灰机媒体-文本语义对齐标注日志

日期：2026-07-09  
用途：按批次记录人工标注阶段性成果，避免只依赖对话上下文。  
对应规格：`docs/superpowers/specs/2026-07-09-huiji-media-visual-taxonomy-labeling-design.md`

## 记录规则

- 本文件记录每轮人工标注结果、用户解释、暂定 `visual_role`、待查文本来源和疑点。
- specs 只保留稳定规则、模块契约和关键样例；本文件保留批次细节。
- 进入 Wiki/RAG 构建层前，应从本文件整理出可审核的结构化报告。
- 当前阶段只读爬虫数据、RAG 处理产物和 MinIO 已有对象，不修改 Milvus、MinIO、MySQL 或向量库。

## Batch 001：角色核心视觉、技能、活动、卡池

### 已确认结论

| 文件名 | visual_role | 人工确认含义 | 备注 |
| --- | --- | --- | --- |
| `L2d_static-300301_hujisheng.webp` | `live2d_static` | 槲寄生原皮 Live2D 图片。 | 角色展示图。 |
| `L2d_static-300901_sufubi_p.webp` | `live2d_static` | 苏芙比 Sotheby 的 Live2D 图片。 | `p` 后缀含义未知，先记录为 `variant=p`。 |
| `Portrait-300301.webp` | `portrait` | 槲寄生原皮立绘。 | 原皮立绘与 Live2D 差异较小，需依文件名和上下文判断。 |
| `Portrait-300302.webp` | `portrait` | 槲寄生洞悉皮肤立绘。 | 皮肤名：熟识橡树之人 / The Druid。 |
| `Spine_static-300301_hujisheng.webp` | `chibi` | 槲寄生原皮小人物形象。 | `Spine` 暂作命名前缀，不解释业务含义。 |
| `Spine_static-300303_hujisheng.webp` | `chibi` | 槲寄生洞悉后皮肤小人物形象。 | 皮肤名：熟识橡树之人 / The Druid。 |
| `Spine_static-300301_hujisheng_s.webp` | `udimo` | 槲寄生原皮尤提姆形象。 | 待命形态，小人物变体。 |
| `Spine_static-300305_hjs_s.webp` | `udimo` | 槲寄生衣着“闹蛾儿 / Lady With Nao'E”的尤提姆形象。 | 同角色不同皮肤的尤提姆品种相近，装饰不同。 |
| `Skill-30030111.webp` | `skill_icon` | 槲寄生一技能“风入林”。 | Attack 攻击卡。 |
| `Skill-30030121.webp` | `skill_icon` | 槲寄生二技能“露渐白”。 | Attack 攻击卡。 |
| `Skill-30030131.webp` | `skill_icon` | 槲寄生大招“林间，静默将至”。 | 至终仪式/大招。 |
| `Banner_荣耀废墟与隐喻指南.png` | `character_story_event_banner` | 虚构集《荣耀废墟与隐喻指南》的角色剧情活动 Banner。 | 角色个人剧情活动。 |
| `Banner_征集·火花雀儿.jpg` | `summon_banner` | 征集“火花雀儿”的卡池 Banner。 | UP：六星可燃点、五星和平乌鲁、五星帕米埃；规则：限时角色征集。 |
| `SummonPool-火花雀儿.png` | `summon_title_logo` | “火花雀儿”卡池标题素材。 | 用于不同尺寸或布局复用。 |

### 已确认文本绑定

| 对象 | 文本 |
| --- | --- |
| 槲寄生洞悉皮肤“熟识橡树之人 / The Druid” | 她回到橡木树梢，像是回到母亲的怀抱。 |
| 槲寄生原皮尤提姆 | 猫类尤提姆，常见。通体漆黑，毛发顺滑，弯月夜中常散发出橡木香气。独居动物，社交倾向弱，攻击性弱，性格柔和，喜好植被，对外界保有好奇心。 |

### 规则与疑点

- `Portrait`、`Spine`、`L2d` 编号不保证一一对应，需要用 `skin_key`、页面文本和人工标注合并。
- 同一视觉资源可能存在 `webp/png/jpg` 多格式版本，不能当成不同业务图。
- 技能图标需要记录技能槽位、卡牌类型、星级/阶段和机制标签。

## Batch 002：头像族横向对比

### 样本

| 序号 | 文件名 | 人工确认含义 | 暂定 visual_role | 说明 |
| ---: | --- | --- | --- | --- |
| 1 | `Headicon_small-300101.png` | 维尔汀的立绘小头像。 | `portrait_avatar_small` | `Headicon_small-*` 当前倾向为立绘/半身视觉裁出的头像。 |
| 2 | `HeadIconSmall-300101.png` | 维尔汀的立绘小头像。 | `portrait_avatar_small` | 原先怀疑 `HeadIconSmall-*` 是小人物头像，本轮证明该族至少存在立绘小头像，需要继续抽样细分。 |
| 3 | `Headicon_small-300301.png` | 槲寄生的立绘小头像。 | `portrait_avatar_small` | 与样本 1 同类。 |
| 4 | `HeadIconSmall-300105.png` | 维尔汀的立绘小头像，但为摘下帽子的形态。 | `portrait_avatar_small` | 同角色不同形态，应记录 `variant` 或 `skin/form`。 |
| 5 | `MonsterHeadIcon-300301.png` | 槲寄生的小人物小头像。 | `chibi_avatar_small` | 虽然前缀是 `MonsterHeadIcon`，但本样本不是敌方独占语义，可能与敌方/镜像使用场景复用。 |

### 本轮修正规则

- `Headicon_small-*` 可稳定视为 `portrait_avatar_small` 的重要命名族。
- `HeadIconSmall-*` 不能简单归为 `chibi_avatar_small`；它也可能是 `portrait_avatar_small`，需要结合图片内容、角色形态和来源上下文继续拆分。
- `MonsterHeadIcon-*` 不能只按文件名前缀定为敌方头像；它可能复用友方小人物头像，实际语义需要结合页面/关卡上下文判断。
- 头像族需要保留 `source_family`，并单独记录 `visual_role`，避免命名族和业务类型混淆。

### 待查文本来源

- `resources_manifest.jsonl` 中对应文件页 `descriptionurl`。
- `wikitext.jsonl` / `data_pages.jsonl` 中是否存在这些头像文件的引用位置。
- 维尔汀不同形态头像是否有明确页面标题、形态名或剧情/系统用途说明。

## Batch 003：大头像、小头像、格式复用与敌方头像

### 样本

| 序号 | 文件名 | 人工确认含义 | 暂定 visual_role | 说明 |
| ---: | --- | --- | --- | --- |
| 1 | `Headicon_large-300301.png` | 槲寄生的 Live2D 大头像。 | `live2d_avatar_large` | 与样本 2 视觉一致，格式不同。此前误归为通用角色大头像，需要修正。 |
| 2 | `Headicon_large-300301.webp` | 槲寄生的 Live2D 大头像。 | `live2d_avatar_large` | 与样本 1 是同一图的不同格式，应归入同一 `visual_asset_key`。 |
| 3 | `Headicon_large-300302.png` | 槲寄生洞悉皮肤“熟识橡树之人 / The Druid”的立绘大头像。 | `portrait_avatar_large` | 与样本 4 属于同角色同皮肤，只是尺寸不同。 |
| 4 | `Headicon_small-300302.png` | 槲寄生洞悉皮肤“熟识橡树之人 / The Druid”的立绘小头像。 | `portrait_avatar_small` | 与样本 3 同皮肤不同尺寸。 |
| 5 | `MonsterHeadIcon-300201.png` | 敌对方的小人物小头像。 | `enemy_chibi_avatar_small` | 可用于敌方单位、敌方镜像、关卡配置。 |

### 本轮修正规则

- `Headicon_large-*` 不能统一归为 `character_avatar_large`。它至少可能包含 `live2d_avatar_large` 和 `portrait_avatar_large`。
- `Headicon_large-300301.png` 与 `Headicon_large-300301.webp` 是同一视觉资源的不同格式，需要用 `visual_asset_key` 聚合。
- 同一皮肤可能同时存在大头像和小头像，例如 `Headicon_large-300302.png` 与 `Headicon_small-300302.png` 都属于槲寄生洞悉皮肤“熟识橡树之人 / The Druid”。
- 英文名按规范归一为 `The Druid`；用户输入中出现的 `The Druidd` 视为同一皮肤的拼写误差。

### 流程改进

后续每轮标注前，先给出模型自主识图预判，再向用户提问。日志中记录：

```text
model_guess
user_label
correction
confidence
```

这样可以利用模型预判暴露细节遗漏，同时以用户标注作为最终真值。

## Batch 004：Skill 前缀下的功能牌 / 场地机制牌

### 样本

| 序号 | 文件名 | model_guess | user_label | correction | 暂定 visual_role |
| ---: | --- | --- | --- | --- | --- |
| 1 | `Skill-103001.png` | 角色技能卡面，可能是一技能或星级阶段卡。 | 活动“行至摩卢旁卡”的特殊功能牌，群星之力，名称为“日蚀”。 | 不是角色技能，不归属角色；属于场地效果/活动机制提供的 Versatile 卡。 | `event_versatile_card_art` |
| 2 | `Skill-103002.png` | 同角色同组技能卡面，可能是二技能。 | 活动“行至摩卢旁卡”的特殊功能牌，群星之力，名称为“月蚀”。 | 不是角色技能；属于群星之力卡组。 | `event_versatile_card_art` |
| 3 | `Skill-103003.png` | 同角色大招/至终仪式卡面。 | 活动“行至摩卢旁卡”的特殊功能牌，群星之力，名称为“一次完满”。 | 不是角色大招；属于场地机制牌。 | `event_versatile_card_art` |
| 4 | `Skill-103004.png` | 另一角色或机制技能卡面，可能是 Buff/Debuff/机制卡。 | 通用功能牌，通常代表正向功能。 | 不属于普通角色手牌；由场地机制提供，下标为 Versatile。 | `generic_versatile_card_art` |
| 5 | `Skill-103005.png` | 与样本 4 同组或同机制，可能是特殊效果卡。 | 通用功能牌，通常代表负面功能。 | 不属于普通角色手牌；由场地机制提供，下标为 Versatile。 | `generic_versatile_card_art` |

### 人工解释

图 1、图 2、图 3 都属于一次活动“行至摩卢旁卡”的特殊功能牌，类型为 `Versatile`。它们是场地效果，不归属于某个角色。自 `JMP-03` 关卡开始，可以在配置队伍时择选“群星之力”。完成关卡内“天穹的昭示”特别任务即可获得一张群星之力卡。群星之力卡不占用行动点，使用后开启“幻境”，得到相应加成。

正篇主线中群星之力共有三种，需要通过“天穹低语”解锁：

- 日蚀
- 月蚀
- 一次完满

“今日寻星”中另有一种特别的群星之力“转变的星象”。

图 4、图 5 属于通用功能牌：

- 图 4 通常代表正向功能。
- 图 5 通常代表负面功能。
- 另有中性或治疗类功能牌。

这类卡通常带有 `Versatile` 下标，表示它们由场地机制提供，不是普通角色手牌。

### 本轮修正规则

- `Skill-*` 前缀不能直接等同于角色技能卡。它可能包含角色技能、活动机制牌、场地效果牌、通用功能牌。
- `Versatile` 应作为独立 `card_type` 记录。
- 功能牌需要记录 `provider_type`，例如 `field_mechanic`、`event_mechanic`、`stage_mechanic`。
- 活动专属功能牌需要绑定 `event_name`、`stage_key`、机制名和解锁/获取规则。
- 通用功能牌需要记录功能倾向，例如 `positive`、`negative`、`neutral`、`healing`。

### 待查文本来源

- `JMP-03` 页面及其关联关卡说明。
- “行至摩卢旁卡”相关活动/主线页面。
- “天穹的昭示”“天穹低语”“今日寻星”“转变的星象”相关页面或 wikitext。
- 文件页中 `Skill-103001` 至 `Skill-103005` 的引用位置。

## Batch 005：敌方角色通用技能卡面

### 样本

| 序号 | 文件名 | model_guess | user_label | correction | 暂定 visual_role |
| ---: | --- | --- | --- | --- | --- |
| 1 | `Skill-1101.png` | 角色手牌，偏 Attack 攻击卡，枪击/射击主题。 | 敌方角色的通用技能卡面。 | 不归属友方角色；同一卡面可能有不同名字/效果。 | `enemy_generic_card_art` |
| 2 | `Skill-1102.png` | 与样本 1 同组，角色手牌，偏 Attack 或多段攻击。 | 敌方角色的通用技能卡面。 | 卡牌类型不能仅凭图案判断。 | `enemy_generic_card_art` |
| 3 | `Skill-1103.png` | 与样本 1、2 同组，可能是 Buff/治疗/强化类技能。 | 敌方角色的通用技能卡面。 | 是否 Attack/Debuff/Buff 要看页面效果描述。 | `enemy_generic_card_art` |
| 4 | `Skill-1104.png` | 与样本 1-3 同组，可能是大招/至终仪式，炮击主题。 | 敌方角色的通用技能卡面。 | 敌方通用卡面可有不同名字和效果。 | `enemy_generic_card_art` |
| 5 | `Skill-1201.png` | 另一角色手牌，偏 Attack 或攻击机制。 | 敌方角色的通用技能卡面。 | 属于敌方通用技能视觉，不应按友方角色技能处理。 | `enemy_generic_card_art` |

### 用户补充样例

用户补充截图显示，除本批 5 张外，类似图案也包括更多敌方通用卡面，例如：

- 枪击/抹黑手法类视觉：可对应“惯用的抹黑手法”“捕风捉影”“混淆视听”“猛烈抢舞”“抨击”“挥棒”等不同名称与效果。
- 橙色怪影类视觉：可对应“勾尾的曲解”“讹言啃食”“形迹捕捉”等不同名称与效果。
- 灰白机械类视觉：可对应“制伏型系统β”“违规制裁”“威慑管控”“高频麻醉电流器”“越限警戒”“磁力充沛”等不同名称与效果。

这些卡面可能显示 `Attack`、`Debuff`、`Buff` 等下标，但不能仅凭卡面图案统一判定。最终 `card_type`、效果、状态词和数值必须来自对应页面附带描述。

### 本轮修正规则

- `enemy_generic_card_art` 是独立视觉类型，用于敌方角色/敌方单位的通用技能卡面。
- 同一敌方通用卡面可以对应多个技能名和效果，标注时应允许一图多义。
- 该类资源的核心连接不应是 `character_id + skill_slot`，而应优先使用 `enemy_id / encounter_id / stage_key / skill_name / effect_text`。
- `card_type` 不从图像硬推，应从页面描述或卡面下标读取；如果冲突，以页面效果描述为准。
- 这类卡面和 `event_versatile_card_art` 不同：前者是敌方通用技能视觉，后者是场地/活动机制提供的功能牌。

### 待查文本来源

- 敌方单位页面或关卡页面中的技能表。
- `Skill-1101` 至 `Skill-1201` 文件在 `wikitext.jsonl` / `data_pages.jsonl` 中的引用位置。
- 页面效果描述中的名称、星级、卡牌类型、状态词、数值和目标范围。

## Batch 006：敌方通用卡面的视觉子族

### 样本

| 序号 | 文件名 | model_guess | user_label | correction | 暂定 visual_role | enemy_visual_family |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | `Skill-1202.png` | 敌方通用技能卡面，橙色怪影系。 | 敌方通用卡牌，魔精类。 | “橙色怪影系”应更准确称为“魔精类”，偏野兽形态。 | `enemy_generic_card_art` | `manus_vindictae_beastlike` / 魔精类 |
| 2 | `Skill-1203.png` | 敌方通用技能卡面，橙色怪影系。 | 敌方通用卡牌，魔精类。 | 同上。 | `enemy_generic_card_art` | `manus_vindictae_beastlike` / 魔精类 |
| 3 | `Skill-1204.png` | 敌方通用技能卡面，橙色怪影系。 | 敌方通用卡牌，魔精类。 | 同上。 | `enemy_generic_card_art` | `manus_vindictae_beastlike` / 魔精类 |
| 4 | `Skill-1205.png` | 敌方通用技能卡面，橙色怪影系，同组变体。 | 敌方通用卡牌，魔精类。 | 同上。 | `enemy_generic_card_art` | `manus_vindictae_beastlike` / 魔精类 |
| 5 | `Skill-1301.png` | 另一组敌方通用技能卡面，音乐/声波/喊叫主题。 | 敌方通用卡牌，重塑之手类。 | 蓝色系更准确是“重塑之手类”，偏敌方阵营人类形态，装饰物较多。 | `enemy_generic_card_art` | `manus_vindictae_humanoid` / 重塑之手类 |

### 用户补充规则

- 橙色怪影系应标为“魔精类”，偏野兽形态。
- 蓝色音乐/声波系应标为“重塑之手类”，偏敌方阵营人类形态，身上装饰物较多。
- 之前坦克、枪击等视觉更偏“军队系”，敌方几乎是人类。
- 这些都属于敌方通用卡牌；具体 `Attack / Debuff / Buff` 和效果描述仍需查页面文本。

### 本轮修正规则

- `enemy_generic_card_art` 需要增加视觉子族字段 `enemy_visual_family`。
- `enemy_visual_family` 当前候选：
  - `manus_vindictae_beastlike` / 魔精类：偏野兽形态，多为橙色怪影视觉。
  - `manus_vindictae_humanoid` / 重塑之手类：偏敌方阵营人类形态，装饰物较多，常见蓝色音乐/声波视觉。
  - `military_humanoid` / 军队系：偏人类军队、枪械、坦克、炮击视觉。
- `enemy_visual_family` 只描述视觉/阵营风格，不替代 `enemy_id`、`stage_key`、`skill_name` 和 `effect_text`。

## Batch 007：重塑之手类与岩城帮会通用卡面

### 样本

| 序号 | 文件名 | model_guess | user_label | correction | 暂定 visual_role | enemy_visual_family |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | `Skill-1302.png` | 敌方通用卡面，重塑之手类。 | 正确，重塑之手类。 | 保持。 | `enemy_generic_card_art` | `manus_vindictae_humanoid` / 重塑之手类 |
| 2 | `Skill-1303.png` | 敌方通用卡面，重塑之手类。 | 正确，重塑之手类。 | 保持。 | `enemy_generic_card_art` | `manus_vindictae_humanoid` / 重塑之手类 |
| 3 | `Skill-1304.png` | 敌方通用卡面，重塑之手类。 | 正确，重塑之手类。 | 保持。 | `enemy_generic_card_art` | `manus_vindictae_humanoid` / 重塑之手类 |
| 4 | `Skill-1401.png` | 敌方通用卡面，可能是军队系或红色袭击/暴力系。 | 敌方通用卡面，多数描述中属于帮派“岩城帮会”。 | 不应粗归军队系；新增更具体的岩城帮会子族。 | `enemy_generic_card_art` | `rock_city_gang` / 岩城帮会 |
| 5 | `Skill-1402.png` | 敌方通用卡面，可能与样本 4 同子族。 | 敌方通用卡面，多数描述中属于帮派“岩城帮会”。 | 同上。 | `enemy_generic_card_art` | `rock_city_gang` / 岩城帮会 |

### 用户补充规则

- `Skill-1302`、`Skill-1303`、`Skill-1304` 归入重塑之手类。
- `Skill-1401`、`Skill-1402` 等红色暴力/袭击视觉多数描述中属于帮派“岩城帮会”。
- 岩城帮会是敌方通用卡面的一个更具体视觉/敌方组织子族，不应简单粗归为军队系。

### 本轮修正规则

- `enemy_visual_family` 增加：
  - `rock_city_gang` / 岩城帮会：红色、帮派、袭击、街头暴力视觉。
- 若视觉可落到具体敌方组织，应优先使用具体组织子族；无法确定时才退回 `military_humanoid`、`manus_vindictae_humanoid` 等较粗类别。

## Batch 008：帮派类与第一防线学校在校生

### 样本

| 序号 | 文件名 | model_guess | user_label | correction | 暂定 visual_role | enemy_visual_family |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | `Skill-1403.png` | 敌方通用卡面，岩城帮会。 | 也可能是启明会或鬓影姐妹会；不论哪个会，都是帮派，属于敌对阵营通用卡面。 | 不应强行指定岩城帮会；应先归“帮派类”，具体组织从页面描述确认。 | `enemy_generic_card_art` | `gang_faction` / 帮派类 |
| 2 | `Skill-1404.png` | 敌方通用卡面，岩城帮会。 | 也可能是启明会或鬓影姐妹会；不论哪个会，都是帮派，属于敌对阵营通用卡面。 | 同上。 | `enemy_generic_card_art` | `gang_faction` / 帮派类 |
| 3 | `Skill-1501.png` | 新子族，蓝灰/晶体/审判或执行者风格。 | 通常是“第一防线学校在校生”这一派系的卡面。 | 新增第一防线学校在校生子族。 | `enemy_generic_card_art` | `frontline_school_student` / 第一防线学校在校生 |
| 4 | `Skill-1502.png` | 与样本 3 同子族。 | 通常是“第一防线学校在校生”这一派系的卡面。 | 同上。 | `enemy_generic_card_art` | `frontline_school_student` / 第一防线学校在校生 |
| 5 | `Skill-1503.png` | 与样本 3、4 同子族。 | 通常是“第一防线学校在校生”这一派系的卡面。 | 同上。 | `enemy_generic_card_art` | `frontline_school_student` / 第一防线学校在校生 |

### 用户补充规则

- `Skill-1403`、`Skill-1404` 可能是启明会、鬓影姐妹会或其他帮派组织。当前不要锁死为岩城帮会，统一先归为“帮派类”敌方通用卡面。
- `Skill-1501`、`Skill-1502`、`Skill-1503` 通常是“第一防线学校在校生”派系卡面。

### 本轮修正规则

- `enemy_visual_family` 增加：
  - `gang_faction` / 帮派类：启明会、鬓影姐妹会、岩城帮会等帮派组织通用视觉；具体组织需查页面描述。
  - `frontline_school_student` / 第一防线学校在校生：蓝灰/晶体/学校/学生派系视觉。
- 需要区分 `enemy_visual_family` 与未来可能的 `enemy_org`：
  - `enemy_visual_family`：视觉和风格粗分类。
  - `enemy_org`：页面描述中明确的敌方组织，例如岩城帮会、启明会、鬓影姐妹会、第一防线学校在校生。

## Batch 009：第一防线尾图、中立通用敌方卡面与复用卡

### 样本

| 序号 | 文件名 | model_guess | user_label | correction | 暂定 visual_role | enemy_visual_family |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | `Skill-1504.png` | 第一防线学校在校生，同组强技能/大图。 | 正确。 | 保持。 | `enemy_generic_card_art` | `frontline_school_student` / 第一防线学校在校生 |
| 2 | `Skill-1702.png` | 新子族，灰白几何/建筑/抽象构造物。 | 通用敌方卡面，常用于没有明显势力范围的偏中立对象，如火炮、雕塑、神祗、队友镜像。 | 不应强行新增具体派系；先归为中立/无明显势力范围通用敌方卡面。 | `enemy_generic_card_art` | `neutral_or_unspecified_enemy` / 偏中立或无明显势力范围 |
| 3 | `Skill-1703.png` | 与样本 2 同子族，几何/建筑/碑状物视觉。 | 同样是偏中立或无明显势力范围的通用敌方卡面。 | 同上。 | `enemy_generic_card_art` | `neutral_or_unspecified_enemy` / 偏中立或无明显势力范围 |
| 4 | `Skill-1704.png` | 与样本 2、3 同子族，大图/强技能视觉。 | 同样是偏中立或无明显势力范围的通用敌方卡面。 | 同上。 | `enemy_generic_card_art` | `neutral_or_unspecified_enemy` / 偏中立或无明显势力范围 |
| 5 | `Skill-2001.png` | 军队系，疑似 `Skill-1101` 复用。 | 符合敌方通用卡面逻辑，可视作军队系复用卡面。 | 需要用 `visual_asset_key` 合并同图复用。 | `enemy_generic_card_art` | `military_humanoid` / 军队系 |
| 6 | `Skill-2002.png` | 军队系，疑似 `Skill-1102` 复用。 | 符合敌方通用卡面逻辑，可视作军队系复用卡面。 | 需要用 `visual_asset_key` 合并同图复用。 | `enemy_generic_card_art` | `military_humanoid` / 军队系 |

### 用户补充规则

- 敌方卡面多数只需要归为敌方卡面类即可。
- 具体效果、势力归属和用途通常跟关卡设定强相关，应随 Markdown 文档、网页链接或页面技能描述一起解析。
- 游戏越到后期，此类卡面的适用边界越模糊，不能只靠视觉强行细分。
- 偏中立或无明显势力范围的对象包括火炮、雕塑、神祗、队友镜像等。

### 本轮修正规则

- `enemy_visual_family` 增加：
  - `neutral_or_unspecified_enemy` / 偏中立或无明显势力范围：火炮、雕塑、神祗、队友镜像等，依赖页面上下文判断。
- 敌方通用卡面的细分是辅助字段，不是强制字段；无法稳定细分时保留 `enemy_generic_card_art` 即可。
- 同图复用需要通过 `visual_asset_key` 聚合，例如 `Skill-2001` 与早期枪击卡面可能为同图或近似复用。

## Batch 010：敌方通用卡面的同图复用确认

### 样本

| 序号 | 文件名 | model_guess | user_label | correction | 暂定 visual_role | enemy_visual_family | 复用关系 |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | `Skill-2003.png` | 敌方通用卡面，偏军队 / 普通人形敌方系，可能与 `Skill-2001/2002` 属于同组。 | 复用。 | 作为敌方通用卡面复用记录，不强行新增子类；具体技能名和效果应从页面文本取。 | `enemy_generic_card_art` | `military_humanoid` / 军队系（暂定） | 与前序敌方通用卡面复用，待用 `visual_asset_key` 聚合。 |
| 2 | `Skill-2004.png` | 敌方通用卡面，偏军队 / 火炮 / 机械武器系，也可能归入偏中立对象。 | 复用。 | 作为敌方通用卡面复用记录；若页面上下文指向火炮、机械或无明确势力对象，可回退到 `neutral_or_unspecified_enemy`。 | `enemy_generic_card_art` | `military_humanoid` / 军队系（暂定） | 与前序敌方通用卡面复用，待用 `visual_asset_key` 聚合。 |
| 3 | `Skill-2101.png` | 与 `Skill-1501.png` 同图复用，第一防线学校在校生卡面。 | 复用。 | 确认同图复用。 | `enemy_generic_card_art` | `frontline_school_student` / 第一防线学校在校生 | 复用 `Skill-1501.png`。 |
| 4 | `Skill-2102.png` | 与 `Skill-1502.png` 同图复用，第一防线学校在校生卡面。 | 复用。 | 确认同图复用。 | `enemy_generic_card_art` | `frontline_school_student` / 第一防线学校在校生 | 复用 `Skill-1502.png`。 |
| 5 | `Skill-2103.png` | 与 `Skill-1503.png` 同图复用，第一防线学校在校生卡面。 | 复用。 | 确认同图复用。 | `enemy_generic_card_art` | `frontline_school_student` / 第一防线学校在校生 | 复用 `Skill-1503.png`。 |
| 6 | `Skill-2104.png` | 与 `Skill-1504.png` 同图复用，第一防线学校在校生卡面。 | 复用。 | 确认同图复用。 | `enemy_generic_card_art` | `frontline_school_student` / 第一防线学校在校生 | 复用 `Skill-1504.png`。 |

### 用户补充规则

- 本批 6 张均为复用卡面。
- 对复用卡面不应为每个文件名重复建立新的业务语义；应先用 `visual_asset_key` 合并同图，再通过页面文本区分具体技能名、效果、关卡和敌方单位。
- 第一防线学校在校生卡面已经出现多轮复用，说明 `Skill-*` 文件名只代表素材文件编号，不代表唯一技能语义。

### 本轮修正规则

- `visual_asset_key` 应成为敌方通用卡面标注的关键字段之一，用于合并相同视觉资源。
- `filename` 仍需保留，因为同一视觉资源可能在不同页面、不同技能或不同关卡中以不同文件名出现。
- `enemy_visual_family` 只作为复用视觉的粗分类；最终业务含义必须由 `stage_key / enemy_id / skill_name / effect_text / source_page` 补足。

## Batch 012：敌对势力通用卡面与场地 buff 通用手牌

> Batch 011 的 `Skill-2201` 至 `Skill-2302` 暂未确认，本轮先记录已确认的 Batch 012。

### 样本

| 序号 | 文件名 | model_guess | user_label | correction | 暂定 visual_role | 连接方式 |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | `Skill-2303.png` | 敌方通用卡面，偏中立 / 无明显势力范围，灰白几何构造物。 | 敌对势力通用。 | 归入敌对势力通用卡面；具体势力、技能名和效果仍需查页面文本。 | `enemy_generic_card_art` | `stage_key / enemy_id / skill_name / effect_text / source_page` |
| 2 | `Skill-2304.png` | 敌方通用卡面，偏中立 / 无明显势力范围，同组强技能或大招视觉。 | 敌对势力通用。 | 同上。 | `enemy_generic_card_art` | `stage_key / enemy_id / skill_name / effect_text / source_page` |
| 3 | `Skill-2305.png` | 功能 / 机制图标，金色玫瑰或植物意象，可能是状态、奖励、机制或特殊效果素材。 | 场地牌 / 场地效果通用。 | 绝大部分情况下由场地效果提供，不归属角色或敌方单位。 | `field_generic_card_art` | `stage_key / field_effect_id / mechanic_name / provider_type=field_effect / effect_text` |
| 4 | `Skill-2306.png` | 功能 / 机制图标，蓝色浇水壶，可能和恢复、培育、植物机制、资源生产有关。 | 场地牌 / 场地效果通用。 | 同上。 | `field_generic_card_art` | `stage_key / field_effect_id / mechanic_name / provider_type=field_effect / effect_text` |
| 5 | `Skill-2307.png` | 功能 / 机制图标，幼苗 / 根系，可能和生长、培育、植物机制、生命或持续效果有关。 | 场地牌 / 场地效果通用。 | 同上。 | `field_generic_card_art` | `stage_key / field_effect_id / mechanic_name / provider_type=field_effect / effect_text` |
| 6 | `Skill-2308.png` | 功能 / 机制图标，三叶草 / 藤蔓，可能和植物、幸运、增益或活动机制有关。 | 场地牌 / 场地效果通用。 | 同上。 | `field_generic_card_art` | `stage_key / field_effect_id / mechanic_name / provider_type=field_effect / effect_text` |

### 用户补充规则

- 本批前两张是敌对势力通用卡面。
- 本批后四张是场地牌 / 场地效果通用卡面，绝大部分情况下由场地效果提供。
- 场地牌也是通用资源，不应按文件名直接绑定到角色技能或敌方技能。

### 本轮修正规则

- 新增并采用推荐字段 `visual_role=field_generic_card_art`。
- `field_generic_card_art` 与 `event_versatile_card_art` 的关系：二者都不归属角色；前者更偏场地效果给出的通用卡面，后者更偏活动/关卡机制提供的 Versatile 功能牌。
- 若页面文本明确说明场地牌由某个机制、场地、关卡或事件生成，应优先绑定 `field_effect_id / mechanic_name / stage_key`，而不是绑定人物或敌方单位。

## Batch 013：场地牌通用复用

### 样本

| 序号 | 文件名 | model_guess | user_label | correction | 暂定 visual_role | 连接方式 | 复用关系 |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | `Skill-228101.png` | 通用机制 / 场地效果手牌，黑胶唱片与播放按钮，可能和音乐、播放、节奏、唱片机关有关。 | 场地牌，通用，复用。 | 用户二次纠错：此前“机械类敌对角色技能”判断错误；本批 6 张都是场地牌。 | `field_generic_card_art` | `stage_key / field_effect_id / mechanic_name / provider_type=field_effect / effect_text` | 场地牌复用，待 `visual_asset_key` 聚合。 |
| 2 | `Skill-760001.png` | 通用机制 / 场地效果手牌，三角与眼睛符号。 | 场地牌，通用，复用。 | 同上。 | `field_generic_card_art` | 同上。 | 同上。 |
| 3 | `Skill-760011.png` | 通用机制 / 场地效果手牌，剑形图标。 | 场地牌，通用，复用。 | 同上。 | `field_generic_card_art` | 同上。 | 同上。 |
| 4 | `Skill-760021.png` | 通用机制 / 场地效果手牌，金色花朵。 | 场地牌，通用，复用。 | 同上。 | `field_generic_card_art` | 同上。 | 同上。 |
| 5 | `Skill-760031.png` | 通用机制 / 场地效果手牌，紫色蛇形。 | 场地牌，通用，复用。 | 同上。 | `field_generic_card_art` | 同上。 | 同上。 |
| 6 | `Skill-760041.png` | 通用机制 / 场地效果手牌，树形/枝叶。 | 场地牌，通用，复用。 | 同上。 | `field_generic_card_art` | 同上。 | 同上。 |

### 用户补充规则

- 用户二次纠错：第 13 批 6 张此前看错，全部应归为通用场地牌复用。
- 抽象图标风格本身不能证明是敌方技能；若页面上下文显示它由场地机制提供，应按场地牌绑定。

### 本轮修正规则

- 使用 `field_generic_card_art` 作为“场地牌 / 场地效果通用卡面”的推荐字段名；早前的 `field_buff_generic_card_art` 太窄，后续仅作为历史称呼参考。
- 场地牌复用仍需保留 `filename`，并用 `visual_asset_key` 聚合同图语义。

## Batch 014：场地发牌与 Boss 卡牌

### 样本

| 序号 | 文件名 | model_guess | user_label | correction | 暂定 visual_role | 分类/连接方式 | 复用关系 |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | `Skill-760051.png` | 通用机制 / 场地效果手牌，蓝色晶体或矿石意象。 | 场地发给玩家的通用卡。 | 归入场地牌；这是由场地发给玩家使用的通用卡。 | `field_generic_card_art` | `stage_key / field_effect_id / mechanic_name / provider_type=field_effect / effect_text` | 场地牌复用，待 `visual_asset_key` 聚合。 |
| 2 | `Skill-760061.png` | 通用机制 / 场地效果手牌，红色圆盘与爆裂符号。 | Boss 卡牌。 | 不归入场地牌；属于不同 Boss 的卡牌，也常以玩家队友“背后灵”的形式出现。 | `boss_card_art` | `boss_id / boss_name / encounter_id / stage_key / skill_name / effect_text / can_appear_as_back_spirit` | Boss 卡牌复用，待 `visual_asset_key` 聚合。 |
| 3 | `Skill-760071.png` | 通用机制 / 场地效果手牌，灰色断裂管道或装置。 | Boss 卡牌。 | 同上。 | `boss_card_art` | `boss_id / boss_name / encounter_id / stage_key / skill_name / effect_text / can_appear_as_back_spirit` | Boss 卡牌复用，待 `visual_asset_key` 聚合。 |
| 4 | `Skill-760081.png` | 通用机制 / 场地效果手牌，蓝色棱镜 / 三角镜面。 | Boss 卡牌。 | 同上。 | `boss_card_art` | `boss_id / boss_name / encounter_id / stage_key / skill_name / effect_text / can_appear_as_back_spirit` | Boss 卡牌复用，待 `visual_asset_key` 聚合。 |
| 5 | `Skill-760082.png` | 与样本 4 视觉几乎一致，可能是同一机制的不同尺寸、不同裁切或同图复用。 | Boss 卡牌。 | 与样本 2/3/4 同属 Boss 卡牌；该 Boss 有两个形态，因此存在两张牌。 | `boss_card_art` | `boss_id / boss_name / boss_form / encounter_id / stage_key / skill_name / effect_text / can_appear_as_back_spirit` | Boss 双形态卡牌，待页面文本确认 form。 |
| 6 | `Skill-760091.png` | 通用机制 / 场地效果手牌，红色双剑。 | Boss 卡牌。 | 与样本 5 同属一个拥有两个形态的 Boss 的卡牌。 | `boss_card_art` | `boss_id / boss_name / boss_form / encounter_id / stage_key / skill_name / effect_text / can_appear_as_back_spirit` | Boss 双形态卡牌，待页面文本确认 form。 |

### 用户补充规则

- `Skill-760051.png` 是场地发给玩家的卡牌，同样是通用卡。
- `Skill-760061.png`、`Skill-760071.png`、`Skill-760081.png` 是不同 Boss 的卡牌，也常以玩家队友“背后灵”的形式出现。
- `Skill-760082.png`、`Skill-760091.png` 与样本 2/3/4 同样是 Boss 卡牌；其中这个 Boss 有两个形态，因此有两张牌。

### 本轮修正规则

- 新增 `visual_role=boss_card_art`。
- Boss 卡牌不同于普通敌方通用卡面：它应优先绑定到 `boss_id / boss_name / encounter_id / stage_key`，并记录是否可作为玩家队友“背后灵”出现。
- 若 Boss 存在多形态，应增加 `boss_form` 或等价字段，避免把不同形态的卡牌误合并。
- 场地发给玩家的通用卡仍使用 `field_generic_card_art`，与 Boss 卡牌分开。

## Batch 016：薪血机制、场地牌与未确认活动专属卡

> Batch 015 暂不清楚，可能是某个活动的专属卡牌，未记录为已确认分类。

### 样本

| 序号 | 文件名 | model_guess | user_label | correction | 暂定 visual_role | 连接方式 | 备注 |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | `Skill-760098.png` | 金色太阳 / 托举意象，可能是场地牌、启示效果展示卡面，或某个活动专属机制卡。 | 应该是场地牌。 | 归入场地牌，仍需页面上下文确认具体机制名。 | `field_generic_card_art` | `stage_key / field_effect_id / mechanic_name / provider_type=field_effect / effect_text` | 通用或复用素材，待 `visual_asset_key` 聚合。 |
| 2 | `Skill-760100.png` | 红色吊坠 / 血滴 / 水晶，可能是活动专属机制卡，或和“薪血/血量消耗”相关。 | 薪血队的牌。 | 归入薪血队机制卡面。 | `bloodtithe_team_card_art` | `mechanic_name=薪血 / team_archetype=薪血队 / related_character_ids[] / consume_rule / effect_text / source_page` | 另有一张爱心形状态展示图，用于标注当前薪血层数，常与相关角色关联。 |
| 3 | `Skill-760101.png` | 蓝色音符卡面，可能是同一活动机制的一组音符牌，偏场地牌或活动专属卡。 | 不确定，可能和术具队有关，也可能是场地 buff。 | 暂不确认。 | `unknown_activity_or_field_card_art`（待定） | `source_page / mechanic_name / effect_text` | 原 Wiki 中未展示这三张牌的界面。 |
| 4 | `Skill-760102.png` | 金色音符卡面，可能和样本 3 同组，不同颜色代表不同效果类型或等级。 | 不确定，可能和术具队有关，也可能是场地 buff。 | 暂不确认。 | `unknown_activity_or_field_card_art`（待定） | `source_page / mechanic_name / effect_text` | 同上。 |
| 5 | `Skill-760103.png` | 绿色音符卡面，可能和样本 3/4 同组，不同颜色代表不同效果类型或等级。 | 不确定，可能和术具队有关，也可能是场地 buff。 | 暂不确认。 | `unknown_activity_or_field_card_art`（待定） | `source_page / mechanic_name / effect_text` | 同上。 |
| 6 | `Skill-760104.png` | 空白圆环 / 音乐节拍底图，可能是同组音符牌的底板、占位或特殊状态展示。 | 应该是场地的复用素材。 | 归入场地牌复用素材。 | `field_generic_card_art` | `stage_key / field_effect_id / mechanic_name / provider_type=field_effect / effect_text` | 可能是音符组底板、占位或场地机制复用素材。 |

### 用户补充规则

- `Skill-760098.png` 应该是场地牌。
- `Skill-760100.png` 是薪血队的牌，和“消耗所有薪血、回复己方全体消耗薪血数量百分比生命”这类效果相关。
- 薪血队还有一张爱心形状态展示图，用于标注当前薪血层数，常与截图中的角色关联；这类状态展示图不应误认为普通手牌。
- `Skill-760101.png`、`Skill-760102.png`、`Skill-760103.png` 可能与术具队有关，术具队以演奏乐器进行对战；也可能只是场地 buff。原 Wiki 中没有展示这三张牌的界面，因此暂不确认。
- `Skill-760104.png` 应该是场地复用素材。

### 本轮修正规则

- 新增 `visual_role=bloodtithe_team_card_art` 和 `bloodtithe_status_display_art`。
- 薪血机制应记录 `team_archetype=薪血队`、相关角色、薪血层数、消耗规则、回复或伤害效果、来源页。
- 对未在原 Wiki 页面展示的素材，不能只靠文件名或图案强行定类，应保留 `unknown_activity_or_field_card_art` 待查状态，并在后续通过 Markdown 引用位置或页面文本确认。
