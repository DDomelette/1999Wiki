# Huiji RAG Provenance 与 Shadow 构建 Runbook

## 1. 当前契约

- 唯一正式 RAG 来源是 `data/huiji/res1999` 的 Huiji crawler snapshot。
- `huiji.enabled` 必须为 `true`，`huiji.source_mode` 必须为 `huiji_crawler`。
- 活动 collection 由 settings 和已安装 baseline 共同固定。
- 旧本地语料 CLI 和模块已移除，不是回滚机制。
- shadow 构建只创建新 collection：不激活、不覆盖、不删除。

## 2. 启动前检查

- Milvus、MinIO、MySQL 已启动。
- `data/processed/huiji/dev` 中 parent、child、media 与两个 BM25 artifacts 完整。
- `.env` 提供运行所需凭据，但凭据不得写入 evidence。
- crawler 凭据只存放于 `.local/huiji/credentials/config.dat`。

```powershell
python scripts\audit_external_paths.py
python scripts\audit_credential_secrecy.py
python scripts\verify_huiji_runtime.py
```

verifier 退出码：

| Exit | 含义 |
|---:|---|
| 0 | provenance 通过，可加载 RAG |
| 2 | 数据或配置漂移，阻断加载 |
| 3 | verifier 异常，fail closed |

## 3. 完整离线审计

```powershell
$RunId = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '-huiji-source'
$RunDir = Join-Path 'eval\huiji_provenance' $RunId
python scripts\audit_huiji_provenance.py audit `
  --run-dir "$RunDir\audit" `
  --candidate-baseline "$RunDir\baseline.candidate.v1.json"
```

只有 audit `status=pass` 且 source/media/BM25/Milvus mismatch 全部为零，candidate 才可进入审阅。出现冲突时停止，查明原因并扩大相关实体、前缀和消费者检查范围。

## 4. 安装 Baseline

人工核对 candidate 只包含项目内相对路径、哈希、计数、schema 和 collection 契约后执行：

```powershell
python scripts\audit_huiji_provenance.py install-baseline `
  --candidate "$RunDir\baseline.candidate.v1.json" `
  --output config\provenance\huiji-dev.v1.json
```

安装使用 create-new 语义。目标已存在时先比较 SHA-256；不一致则停止，不覆盖。

## 5. 创建 Shadow Collection

目标必须是明确的新名称，不能等于活动名称或任何现有 collection：

```powershell
$Shadow = 'text_child_bge_m3_shadow_' + ($RunId.ToLower() -replace '[^a-z0-9_]', '_')
python scripts\build_huiji_index.py `
  --collection-name $Shadow `
  --run-dir "$RunDir\shadow-build"
```

构建后验证 schema、row count、全部 primary IDs 与非向量业务字段指纹。成功或失败的 shadow 均登记保留；不激活、不删除、不使用同名覆盖重试。

## 6. 受保护状态对账

构建或代码变更前：

```powershell
python scripts\verify_huiji_provenance_acceptance.py snapshot `
  --output "$RunDir\protected.pre.v2.json"
```

变更后：

```powershell
python scripts\verify_huiji_provenance_acceptance.py compare `
  --before "$RunDir\protected.pre.v2.json" `
  --output "$RunDir\protected.compare.v2.json"

python scripts\verify_huiji_provenance_acceptance.py sample-active `
  --output "$RunDir\active-source-sample.v1.json"
```

活动 Milvus、两个 MinIO bucket、当前 Wiki MySQL 或正式 artifacts 的非授权漂移都会阻断验收。不要删除 MinIO orphan、`a-bucket` 对象或任何现有 collection。

## 7. 服务恢复原则

- runtime gate 失败：保持 health-only，修复原因后重新审计。
- shadow 构建失败：活动 collection 不变，保留失败 evidence。
- baseline 安装失败：保留 candidate，不覆盖已安装 baseline。
- 不恢复退休语料链路，不自动创建 artifacts，不自动切换 collection。

## 8. 全链路质量评估

provenance 通过后再运行回答质量评估：

```powershell
python scripts\evaluate_rag_full_chain.py preflight `
  --base-url http://127.0.0.1:8000 `
  --output eval\rag_full_chain\preflight.v1.json

python scripts\evaluate_rag_full_chain.py run `
  --base-url http://127.0.0.1:8000 `
  --seed 1999 `
  --output-root eval\rag_full_chain
```

Planner、回答 grounding、媒体协议和性能问题不能替代或豁免 provenance 门禁。
