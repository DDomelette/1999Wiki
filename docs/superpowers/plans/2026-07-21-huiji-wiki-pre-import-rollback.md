# Huiji Wiki Pre-Import Rollback Receipt 实施计划

日期：2026-07-21  
状态：已完成（2026-07-21）  
执行模式：在现有工作区单线程执行，不使用子代理，不清理或回滚其他线程改动。Plan 是本轮强制验收门槛；任一 P0 未闭合均不得签发 passing receipt。

依据 Spec：`docs/superpowers/specs/2026-07-21-huiji-wiki-pre-import-rollback-design.md`  
Spec SHA-256：`8a5511cc9d052ce32d4b207b8e88615c40e03eef75511482e7a73e329328cefe`

## 1. 目标范围

本轮必须完成以下 33 条 P0：

- `AUTH-P0-01..06`
- `DUMP-P0-01..04`
- `INVENTORY-P0-01..05`
- `RESTORE-VERIFY-P0-01..06`
- `RECEIPT-P0-01..06`
- `RESTORE-ENTRY-P0-01..06`

本轮输出：

1. 可复用的 MySQL inventory、dump、隔离恢复与 receipt 实现；
2. 默认 dry-run、强授权的恢复入口；
3. 正式 Wiki MySQL 的不可覆盖逻辑 dump；
4. 同镜像、无网络、无端口临时 MySQL 的真实恢复演练；
5. `huiji.wiki-rollback-receipt/v1` passing receipt；
6. 33 条 P0 的机械验收矩阵；
7. 交付 RAG 的 receipt 路径与文件 SHA-256。

本轮禁止：

- 对正式 `reverse1999-main-mysql/reverse1999_wiki` 执行 restore 或任何 DDL/DML；
- 执行 Candidate F importer 或 media v3 migration apply；
- 创建或修改 `active_build.v1.json`；
- 切换 Milvus collection；
- 上传、删除或迁移 MinIO 对象；
- 修改 Candidate F、compatibility receipt、activation proposal 或 crawler artifacts；
- 把 test-only receipt 交付 RAG。

## 2. 冻结输入

执行前必须复核，任一不一致即停止并回到审核：

| 输入 | 路径 | 冻结值 |
|---|---|---|
| Candidate F manifest | `data/processed/huiji/crawler-v3-20260721t051246z/build_manifest.json` | SHA-256 `293410a1da4909e6b07e3f755ba0b4ba10b7008152330d5e2f98bcf93a573b5f` |
| Wiki compatibility receipt | `eval/huiji_wiki_v3_compatibility/20260720T162923Z/wiki_media_v3_compatibility_receipt.v1.json` | SHA-256 `b0c82cbaa77303819ee93f600c2f4518152984580bb36d636e0d5063a67ec56d` |
| Activation proposal | `data/processed/huiji/activation/proposals/candidate-f-review-20260721t071308z/activation_proposal.v1.json` | SHA-256 `ce5e6966b80f0b9f1c2300e95866a7d0b9b8d9e108333311f0f92a8d27af1536` |
| Active pointer | `data/processed/huiji/activation/active_build.v1.json` | 执行前后均不存在 |
| 正式 MySQL | Docker `reverse1999-main-mysql` / DB `reverse1999_wiki` | 容器、镜像、server version 在运行时重新 pin |

## 3. 计划修改位置

| 位置 | 用途 |
|---|---|
| `src/huiji_wiki/mysql_inventory.py` | 动态 schema 枚举、标识符引用、类型化长度前缀编码、流式表摘要、DDL/行数/inventory 比较 |
| `src/huiji_wiki/mysql_rollback.py` | 固定 authority、Docker 命令封装、dump、隔离恢复生命周期、canonical receipt、failure evidence |
| `scripts/build_wiki_mysql_rollback_receipt.py` | 仅面向正式 authority 的 pre-import receipt 生成入口 |
| `scripts/restore_wiki_mysql_from_receipt.py` | 默认 dry-run、强授权 apply、emergency receipt 与恢复后验证入口 |
| `tests/test_huiji_wiki_mysql_inventory.py` | inventory 编码、排序、哈希与异常测试 |
| `tests/test_huiji_wiki_mysql_rollback.py` | authority、dump、Docker 生命周期、receipt 与失败路径测试 |
| `tests/test_huiji_wiki_mysql_rollback_scripts.py` | 两个 CLI 的参数、安全门和退出码测试 |
| `eval/huiji_wiki_rollback/<receipt_id>/` | source/restored inventory、验证结果、P0 matrix、passing receipt 或 failure evidence |
| `backups/wiki-mysql/pre-import/<receipt_id>/` | create-new `reverse1999_wiki.sql` dump |

不修改 Wiki importer、repository、API、React、RAG `_state`、Milvus 或 MinIO 客户端。

## 4. 强制检查点

| 检查点 | Specs | 自动化门槛 | 真实数据门槛 | 失败表现 |
|---|---|---|---|---|
| C1 Authority 与凭据 | `AUTH-P0-01..06` | authority/path/credential/owned-test-container 测试 | 正式容器身份和同镜像 pin 成功；stdout/stderr 无密钥 | 通用 source override、路径逃逸、明文凭据或非本次临时容器被接受即失败 |
| C2 无歧义 Inventory | `INVENTORY-P0-01..05` | NULL/文本 NULL、控制字符、二进制、复合主键、顺序、无主键测试 | 正式库全部 base table 动态枚举，singleton snapshot 可解析 | 近似行数、TSV 碰撞、漏表、无稳定主键或 snapshot 非 singleton 即失败 |
| C3 不可覆盖 Dump | `DUMP-P0-01..04` | 必选参数、skip locks、二进制 create-new、漂移阻断测试 | 正式库单事务 dump 完成且前后 inventory 一致 | 覆盖旧 dump、文本重编码、锁表、前后漂移或 dump pin 不符即失败 |
| C4 隔离恢复 | `RESTORE-VERIFY-P0-01..06` | 容器冲突、无网络/端口、readiness、恢复、差异、finally 清理测试 | 同正式镜像完整恢复；DDL/行数/data/inventory hash 全一致 | 端口发布、镜像不符、任一差异、残留容器/tmpfs 或错误签发 receipt 即失败 |
| C5 Passing Receipt | `RECEIPT-P0-01..06` | canonical JSON、内部 hash、文件 hash、sidecar pin、create-new 测试 | 固定输入和正式 inventory 签发前后不变 | 缺 pin、hash 不可复算、failure 文件冒充 passing 或 authority 漂移即失败 |
| C6 恢复入口 | `RESTORE-ENTRY-P0-01..06` | dry-run 默认、授权参数、self-pin、test-only emergency/apply 测试 | 正式容器仅运行 dry-run；apply 只在工具自建临时容器验收 | 正式库 mutation、缺授权仍执行、跳过 emergency receipt 或恢复后不验 hash 即失败 |
| C7 受保护状态 | 全部 P0 | 禁用依赖/命令审计 | Candidate F、pointer、正式 MySQL、MinIO、Milvus 未被本任务写入 | 发现任一越界写操作即整轮失败 |
| C8 回归 | 全部 P0 | 新增测试、Wiki 后端回归、全量 pytest | `/api/wiki/health` 在任务前后保持可读 | 新增测试或既有 Wiki/RAG 测试失败即不得交付 |
| C9 RAG 交付 | `RECEIPT-P0-06` | P0 matrix 33/33、receipt reload 校验 | 只交付 passing receipt 相对路径和文件 SHA-256 | 交付 dump、test-only/failure receipt 或未闭合矩阵即失败 |

## 5. TDD 执行步骤

每个步骤固定遵循：写失败测试 → 运行确认失败原因正确 → 最小实现 → 运行目标测试 → 更新本步骤检查点。禁止先写实现再补测试。

### Step 0：建立执行前基线

- 对应 Specs：全部 P0 的受保护状态前置。
- 只读操作：
  - 复算 Spec 和三份冻结输入 SHA-256；
  - 确认 active pointer 不存在；
  - 读取正式容器 ID、镜像 ID、server version、健康状态和 Compose SHA-256；
  - 动态列出正式库表集合、精确行数和 `wiki_import_snapshots`；
  - 记录相关容器身份及现有 Wiki health；
  - 记录工作区已有变更，仅用于避免覆盖，不执行 git 清理。
- 输出：内存中的 baseline；只有执行流程成功后才进入 passing receipt 的 protected-state compare。
- 门槛：冻结输入、容器或 snapshot 与 Spec 不一致时停止，不自动接受新状态。

### Step 1：TDD 实现 Authority、路径和命令边界

- 对应 Specs：`AUTH-P0-01..06`。
- 先写失败测试：
  - 正式 passing authority 只能是 `reverse1999-main-mysql/reverse1999_wiki`；
  - receipt ID 非法、绝对路径、`..`、symlink/junction 逃逸、输出冲突均拒绝；
  - 命令模型不接受密码字段，也不在异常文本中输出容器环境；
  - 未被当前运行登记、存在端口或网络的容器不能成为 test-only source；
  - test-only receipt schema/status 不能通过 RAG handoff validator。
- 最小实现：
  - 固定 `SourceAuthority`、`OwnedTestAuthority` 和路径解析函数；
  - 正式脚本不提供 source container/database override；
  - 源库客户端通过容器内 `MYSQL_ROOT_PASSWORD` 环境变量名工作，不把值带回宿主或写入命令参数；
  - 临时 MySQL 使用 `--network none`、不发布端口、`MYSQL_ALLOW_EMPTY_PASSWORD=yes` 和 `/var/lib/mysql` tmpfs，不产生宿主凭据。
- 测试命令：
  - `pytest -q tests/test_huiji_wiki_mysql_rollback.py -k "authority or path or credential or test_only"`
- 验收：C1 通过。

### Step 2：TDD 实现规范化 Inventory

- 对应 Specs：`INVENTORY-P0-01..05`。
- 先写失败测试：
  - `NULL` 与字符串 `NULL` 摘要不同；
  - 空字符串、换行、制表符、反斜杠、NUL、UTF-8、多字节文本和 BLOB 均无碰撞；
  - 单主键/复合主键、不同插入顺序产生相同摘要；
  - 改一字节、少一行、多一行、改 DDL 或多一张表必须产生差异；
  - 无主键、重复/非法标识符、读取中断、snapshot 缺字段或多行必须阻断。
- 最小实现：
  - 从 `information_schema` 动态读取 base table、engine、列、类型族、序号和主键顺序；
  - SQL 标识符只由已枚举 metadata 生成并使用反引号转义；
  - 每个值编码为 NULL 标记或 `type + byte_length + hex_bytes`，每行再带长度前缀；
  - 按主键升序流式输入 SHA-256，不把整表载入内存；
  - `SHOW CREATE TABLE`、精确 `COUNT(*)`、data hash 和整体 inventory hash 分层记录；
  - canonical JSON 使用 UTF-8、LF、排序键、尾随单换行。
- 测试命令：
  - `pytest -q tests/test_huiji_wiki_mysql_inventory.py`
- 验收：C2 通过。

### Step 3：TDD 实现不可覆盖 Dump 与漂移检测

- 对应 Specs：`DUMP-P0-01..04`。
- 先写失败测试：
  - 缺任一 mysqldump 必选参数即失败；
  - 命令允许 `--single-transaction` 与 `--skip-lock-tables`，禁止 lock/DDL/DML；
  - dump/eval 目录已存在、文件已存在或写入中断时不覆盖；
  - dump 前后 inventory 不同不生成 passing receipt；
  - PowerShell/文本方式写 dump 被测试拒绝。
- 最小实现：
  - `docker exec` 在正式容器内运行固定 mysqldump 参数；
  - stdout 以二进制流写入同目录 `.partial`，完成后 fsync、SHA-256、exclusive rename；
  - 先 inventory → dump → 后 inventory，三者都成功且前后相同才继续；
  - partial、失败和最终文件命名严格区分，失败时保留 dump 供诊断但绝不生成 passing receipt。
- 测试命令：
  - `pytest -q tests/test_huiji_wiki_mysql_rollback.py -k "dump or drift or create_new"`
- 验收：C3 通过。

### Step 4：TDD 实现隔离恢复生命周期

- 对应 Specs：`RESTORE-VERIFY-P0-01..06`。
- 先写失败测试：
  - 同名容器存在时拒绝且不删除；
  - 镜像 ID 不同、出现网络或端口绑定、readiness 超时均失败；
  - dump hash 不符时不启动 restore；
  - DDL、行数、data hash、表集合任一不同时失败；
  - 成功、异常、超时和 Ctrl+C 路径都调用 finally 清理；
  - 清理失败时不签发 receipt。
- 最小实现：
  - 使用正式镜像 ID启动固定前缀容器；
  - `--rm --network none --tmpfs /var/lib/mysql`，无 `-p/-P`；
  - readiness、建空库、stdin restore、inventory 全部通过 `docker exec`；
  - 容器加本次 operation/owner label，test-only authority 只认当前进程登记的实例；
  - finally 后复查容器不存在、无命名 volume、无端口记录。
- 测试命令：
  - `pytest -q tests/test_huiji_wiki_mysql_rollback.py -k "restore or container or cleanup"`
- 验收：C4 通过。

### Step 5：TDD 实现 canonical Receipt

- 对应 Specs：`RECEIPT-P0-01..06`。
- 先写失败测试：
  - 缺 source/restored inventory、dump、entrypoint、snapshot 或 protected-state pin 时拒绝；
  - 内部 `receipt_sha256`、最终文件 SHA-256、sidecar size/hash 任一改变时 reload 失败；
  - failure/test-only schema 不能被 passing loader 接受；
  - 已有 receipt 路径不能覆盖；
  - Candidate manifest、compatibility receipt、proposal、pointer 或正式 inventory 漂移时拒绝签发。
- 最小实现：
  - 固定输出 sidecars：
    - `source_inventory.before.v1.json`
    - `source_inventory.after.v1.json`
    - `restored_inventory.v1.json`
    - `restore_verification.v1.json`
    - `p0-requirement-matrix.v1.json`
    - `wiki_pre_import_rollback_receipt.v1.json`
  - failure 只写 `verification_failure.v1.json`，schema/status 与 passing 完全不同；
  - receipt pin dump、所有 sidecar、restore entrypoint、正式 authority、installed snapshot 和冻结输入；
  - `receipt_sha256` 对不含自身字段的 canonical payload 计算，交付 SHA 对最终文件字节计算。
- 测试命令：
  - `pytest -q tests/test_huiji_wiki_mysql_rollback.py -k "receipt or canonical or pin or failure"`
- 验收：C5 通过。

### Step 6：TDD 实现恢复入口与 test-only apply

- 对应 Specs：`RESTORE-ENTRY-P0-01..06`。
- 先写失败测试：
  - 无参数、只有 receipt 或缺任一授权参数时只能 dry-run/拒绝；
  - expected file SHA、内部 hash、dump pin、entrypoint self-pin、目标镜像或 DB 不匹配时拒绝；
  - 确认文本必须精确为 `RESTORE reverse1999_wiki FROM <receipt_id>`；
  - emergency receipt 失败时零 mutation；
  - 非本次 owned temp container 不能用于测试 apply；
  - restore 后 inventory 不一致、health 失败或命令中断不得报告成功。
- 最小实现：
  - 默认只加载并复核 receipt，输出计划和将执行的目标，不创建 mutation client；
  - apply 必须同时提供 `--apply`、`--expected-receipt-sha256`、固定目标和确认文本；
  - 创建 mutation 命令前先生成当前目标 emergency rollback receipt；
  - 正式流程顺序固定为：停止 Wiki 写入口 → drop/recreate DB → restore → inventory compare → 重启 8000 → Wiki health；
  - 本轮只对 owned temp container 调用该 apply 路径，正式容器只运行 dry-run。
- 测试命令：
  - `pytest -q tests/test_huiji_wiki_mysql_rollback_scripts.py`
  - `pytest -q tests/test_huiji_wiki_mysql_rollback.py -k "restore_entry or emergency or apply"`
- 验收：C6 通过。

### Step 7：自动化回归门槛

- 对应 Specs：全部 P0。
- 命令：
  - `pytest -q tests/test_huiji_wiki_mysql_inventory.py tests/test_huiji_wiki_mysql_rollback.py tests/test_huiji_wiki_mysql_rollback_scripts.py`
  - `pytest -q tests/test_huiji_wiki_*.py tests/test_wiki_mysql_migration_script.py`
  - `pytest -q`
- 额外静态扫描：
  - 新增代码不得包含 source container/database 通用 CLI override；
  - 不得出现 MinIO/Milvus/importer mutation 调用；
  - 不得把密码拼入命令、日志、evidence 或 receipt；
  - passing/test-only/failure schema 与输出路径必须彼此独立。
- 验收：全部通过，否则不进入真实演练。

### Step 8：真实 Docker/MySQL 只读备份与隔离恢复演练

- 对应 Specs：`AUTH-P0-01..05`、`DUMP-P0-01..04`、`INVENTORY-P0-01..05`、`RESTORE-VERIFY-P0-01..06`、`RECEIPT-P0-01..06`。
- 执行：
  1. 生成唯一安全 `receipt_id`，确认 backup/eval 目录均不存在；
  2. 复核冻结输入、active pointer 缺失、正式容器和 Wiki health；
  3. 运行 `python scripts/build_wiki_mysql_rollback_receipt.py --receipt-id <receipt_id>`；
  4. 观察正式库只读 inventory 与二进制 dump；
  5. 观察临时同镜像容器无网络、无端口恢复；
  6. 核对全部表的 DDL、精确行数和 data hash；
  7. 核对临时容器/tmpfs 清理；
  8. reload passing receipt 并复算全部 pin；
  9. 对正式 authority 运行 `python scripts/restore_wiki_mysql_from_receipt.py --receipt <path>`，只验 dry-run，禁止 `--apply`。
- 必须记录的真实结果：
  - 动态表集合和每表精确行数；
  - source before/after/restored inventory SHA-256；
  - dump 字节数和 SHA-256；
  - 容器/镜像/server/Compose pin；
  - 临时容器无网络/端口与清理证明；
  - installed snapshot 内容；
  - passing receipt 内部 hash 与最终文件 SHA-256。
- 验收：C1-C6 全部在真实数据上通过。

### Step 9：test-only 恢复入口集成验收

- 对应 Specs：`AUTH-P0-06`、`RESTORE-ENTRY-P0-01..06`。
- 执行：
  - 由测试工具创建 owned、无网络、无端口、同镜像临时容器；
  - 先写入受控小型 fixture DB；
  - 对该临时目标生成 `test_only: true` emergency receipt；
  - 使用完整授权参数执行 apply；
  - 验证恢复后 inventory 与指定 receipt 一致；
  - 验证 test-only receipt 不能进入正式输出目录或通过 RAG handoff validator；
  - finally 清理所有测试容器/tmpfs。
- 禁止：把正式 MySQL 作为 apply 目标。
- 验收：C6 真实集成门槛通过。

### Step 10：受保护状态复核与交付

- 对应 Specs：全部 P0，重点 `RECEIPT-P0-05..06`。
- 复核：
  - 三份冻结输入 SHA-256 未变；
  - active pointer 仍不存在；
  - 正式 MySQL final inventory 等于 source before/after；
  - 本任务没有 MinIO、Milvus、Wiki importer 或 migration apply 运行记录；
  - `/api/wiki/health` 仍可读；
  - 无临时容器、命名 volume、partial passing receipt 或泄漏凭据残留；
  - P0 matrix 精确为 33/33 passed，且每项包含代码位置、测试位置、真实证据和失败表现。
- 最终只交付：

  ```text
  wiki_pre_import_rollback_receipt_path
  wiki_pre_import_rollback_receipt_file_sha256
  ```

- 验收：C7-C9 通过。

## 6. P0 覆盖矩阵

| Specs | 实现步骤 | 自动化 | 真实验收 |
|---|---|---|---|
| `AUTH-P0-01` | Step 1 | 固定正式 authority | Step 8 正式容器 pin |
| `AUTH-P0-02` | Step 1 | receipt ID/路径逃逸/create-new | Step 8 新目录 |
| `AUTH-P0-03` | Step 1 | 凭据泄漏/命令参数扫描 | Step 8 stdout/stderr/evidence 扫描 |
| `AUTH-P0-04` | Step 1、3 | 正式命令 allowlist | Step 8 正式库只读运行记录 |
| `AUTH-P0-05` | Step 1、4 | 同镜像/无网络端口/清理 | Step 8 临时容器证明 |
| `AUTH-P0-06` | Step 1、6 | owned test authority/test-only schema | Step 9 test-only apply |
| `DUMP-P0-01` | Step 3 | mysqldump 参数断言 | Step 8 command/options evidence |
| `DUMP-P0-02` | Step 3 | 二进制 create-new | Step 8 dump 路径与字节 pin |
| `DUMP-P0-03` | Step 3、5 | dump metadata/secret omission | Step 8 dump pin |
| `DUMP-P0-04` | Step 3 | inventory 漂移测试 | Step 8 before/after 相同 |
| `INVENTORY-P0-01` | Step 2 | 动态枚举/精确 count | Step 8 全表清单 |
| `INVENTORY-P0-02` | Step 2 | 类型化长度编码/主键排序 | Step 8 全表 data hash |
| `INVENTORY-P0-03` | Step 2 | DDL/row/data 差异测试 | Step 8 source/restored 逐表一致 |
| `INVENTORY-P0-04` | Step 2 | canonical inventory hash | Step 8 三份 inventory pin |
| `INVENTORY-P0-05` | Step 2 | snapshot singleton/字段测试 | Step 8 installed snapshot |
| `RESTORE-VERIFY-P0-01` | Step 4 | 容器名冲突拒绝 | Step 8 唯一容器名 |
| `RESTORE-VERIFY-P0-02` | Step 4 | 无网络/端口断言 | Step 8 Docker inspect |
| `RESTORE-VERIFY-P0-03` | Step 4 | dump pin 后 stdin restore | Step 8 restore evidence |
| `RESTORE-VERIFY-P0-04` | Step 4 | 全维度 compare | Step 8 逐表完全一致 |
| `RESTORE-VERIFY-P0-05` | Step 4 | finally/清理测试 | Step 8 无容器/volume/port 残留 |
| `RESTORE-VERIFY-P0-06` | Step 4、5 | failure schema/非零退出 | Step 8 无伪 passing 文件 |
| `RECEIPT-P0-01` | Step 5 | 必填字段测试 | Step 8 receipt reload |
| `RECEIPT-P0-02` | Step 1、5 | 相对路径/sidecar size+hash | Step 8 所有 pin 复算 |
| `RECEIPT-P0-03` | Step 5 | canonical/internal/file hash | Step 8 字节级复核 |
| `RECEIPT-P0-04` | Step 5、6 | entrypoint self-pin/授权声明 | Step 8 dry-run 验证 |
| `RECEIPT-P0-05` | Step 0、5、10 | protected-state drift 测试 | Step 10 前后状态相同 |
| `RECEIPT-P0-06` | Step 5、10 | handoff validator | Step 10 仅路径+文件 SHA |
| `RESTORE-ENTRY-P0-01` | Step 6 | 默认 dry-run | Step 8 正式 dry-run |
| `RESTORE-ENTRY-P0-02` | Step 6 | 完整授权/确认文本 | Step 9 test-only apply |
| `RESTORE-ENTRY-P0-03` | Step 6 | mutation 前全 pin 验证 | Step 9 篡改阻断 |
| `RESTORE-ENTRY-P0-04` | Step 6 | emergency receipt gate | Step 9 test-only emergency receipt |
| `RESTORE-ENTRY-P0-05` | Step 6 | 固定顺序/失败状态 | Step 9 restore+inventory 验证 |
| `RESTORE-ENTRY-P0-06` | Step 6、9 | dry-run 零 mutation 与完整授权门测试 | Step 8 本轮正式仅 dry-run、Step 9 临时 apply；不削弱未来获授权后的正式恢复能力 |

## 7. 可选任务

本轮不执行 P1。自动 activation 编排只保留未来接口边界，不加入代码路径。

## 8. Deferred / Out of Scope

- `AUTH-P2-01` 跨 MySQL 镜像版本恢复兼容；
- Candidate F 隔离或正式导入；
- media v3 双表 apply；
- active pointer bootstrap；
- activation proposal 重建和 rollback tuple；
- active Milvus 切换；
- MinIO 上传、删除、迁移或 orphan 清理；
- 正式生产 restore；
- Wiki 前端视觉、API 或内容调整。

## 9. 完成后自检表

以下项目初始均为未完成，只有对应代码、自动化和真实证据都存在时才能勾选：

- [x] C1 Authority 与凭据通过。
- [x] C2 无歧义 Inventory 通过。
- [x] C3 不可覆盖 Dump 通过。
- [x] C4 隔离恢复通过。
- [x] C5 Passing Receipt 通过。
- [x] C6 恢复入口通过，正式库仅 dry-run。
- [x] C7 受保护状态无越界写入。
- [x] C8 新增、Wiki 回归和全量 pytest 通过。
- [x] C9 P0 matrix 为 33/33，RAG 交付仅含 receipt 路径和文件 SHA-256。
- [x] Candidate F、active pointer、正式 MySQL、MinIO、Milvus 和 crawler artifacts 未被本任务修改。
- [x] 无临时容器、命名 volume、partial passing receipt 或凭据残留。

只有全部项目勾选后，本 Plan 才能标记完成。

## 10. 执行结果

- 正式 receipt ID：`legacy-dev-pre-candidate-f-20260721b`；最终 receipt 文件 SHA-256 `e245865dd4d790b1b85574ff80d526ca663391578e7afdfa1d096e1977d031c6`。
- 正式 source before/after/restored/final inventory SHA-256：`f29f0f1d09e308d674f5c93a9383891d900085dfcf621815c23107516a689316`，最终差异 `[]`。
- 正式 dump：`45,222,460` bytes，SHA-256 `98e427b3160fed0ce7916755bc7df6d5d82739c7596946b56097b287e1040e11`。
- test-only apply：`rollback-apply-0721d` 通过；证据 SHA-256 `05ef22f81d3f54815ceb139f068e5416f96ee3e73b420cc7b55f291256ea4bb6`。
- 新增回滚测试：`13 passed`；Wiki 定向回归：`105 passed`；全量回归：`1312 passed, 1 skipped`。
- 最终 Wiki health：`ready=true`、`pageCount=7456`、`mediaLinkCount=17527`、`sourceMode=legacy`、`buildVersion=dev`、`stale=false`。
- P0 matrix：`33/33 passed`，每项均包含 implementation、test、evidence 和 failure condition。
- 正式恢复入口仅执行默认 dry-run；没有对正式 MySQL 执行 restore、DDL 或 DML。
