# 1999Wiki Docker 部署手册

本文记录 2026-10-27 实际使用并验证通过的发布方式。日常更新只发布应用镜像，复用服务器上的 MySQL、MinIO、Milvus 和 RAG 文件。

本次发布的精确版本、镜像摘要和验收结果见 [2026-10-27 发布记录](codex/releases/2026-10-27-ui-deployment.md)。更完整的服务器初始化与运维契约见 [Production Deployment Runbook](codex/production-deployment-runbook.md)。

## 1. 环境与目录

| 项目 | 配置 |
| --- | --- |
| 本机项目 | `D:\1999Wiki` |
| GitHub 仓库 | `DDomelette/1999Wiki` |
| 服务器 | `ubuntu@43.139.115.6`，SSH 端口 `22` |
| 本机 SSH 私钥 | `C:\Users\HUAWEI\.ssh\tencent-1999wiki.pem` |
| 网站 | `https://www.ddagent.cloud`、`https://ddagent.cloud` |
| 镜像仓库 | `ccr.ccs.tencentyun.com/1999wiki_code` |
| 后端镜像名 | `1999wiki-backend` |
| 前端镜像名 | `1999wiki-frontend` |
| 服务器平台 | `linux/amd64` |
| blue 端口 | 后端 `18100`，前端 `18180` |
| green 端口 | 后端 `18200`，前端 `18280` |

服务器目录：

```text
/srv/1999wiki/
  runtime-bundle/deploy/       Compose、预检、部署、切换和回滚脚本
  protected/app.env           应用凭据与运行配置
  protected/infra.env         基础设施配置
  protected/caddy.env         网站域名和媒体代理配置
  releases/sha-xxxxxxx/        发布清单、镜像身份和槽位配置
  deploy-state/active.env     当前活动版本与回滚目标
  deploy-state/snapshots/     受保护的应用和发布配置快照
  rag-artifacts/              只读 RAG 运行文件
  mysql/ minio/ etcd/ milvus/  持久数据
```

公网由宿主机 Caddy 接入，`/etc/caddy/active-upstream.caddy` 指向活动槽位的前端端口。前端容器中的 Caddy 再转发 API 到同一槽位的后端。

服务器只运行镜像和运维脚本。镜像构建、npm、测试和源码开发在本机或 GitHub Actions 完成。

## 2. 冻结要发布的源码

1. 查看 `git status --short`，明确本次发布范围。
2. 创建 `codex/` 前缀的发布分支，只提交需要上线的文件。
3. 如工作区同时有其他修改，使用独立工作树，或先通过临时 Git 索引生成发布提交；不要把其他修改一并提交，也不要重置用户的工作区。
4. 推送发布分支，并记录完整 40 位 commit。

PowerShell 中可从已冻结的提交生成版本号：

```powershell
$releaseCommit = (git rev-parse HEAD).Trim()
$releaseTag = 'sha-' + $releaseCommit.Substring(0, 7)
$backendRepo = 'ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-backend'
$frontendRepo = 'ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-frontend'
```

前后端使用同一发布版本。`sha-*` 标签一旦发布就不能覆盖；有任何源码或打包方式调整，都使用新的提交和标签。

## 3. 发布前验证

前端在 `frontend/react-app` 执行：

```powershell
npm ci
npm test
npm run build
```

UI 改动还应检查桌面和手机上的首页、导航、聊天输入、长消息滚动、推荐问题及 Wiki 路由。生产环境的真实聊天要在上线验收时再验证。

后端和部署检查以 GitHub Actions 的完整 Python 测试为准。本机 Windows 使用项目的 Python 3.11 环境运行定向测试：

```powershell
& 'D:\1999Wiki\.venv-windows\Scripts\python.exe' -m pytest -q <相关测试文件>
```

后端镜像中的 `RUN python -c "import backend.main"` 是必要构建门禁。不能通过删除该门禁来绕过缺失依赖。

## 4. 首选路径：GitHub Actions 构建发布

工作流：`.github/workflows/publish-images.yml`。

仓库需要已有的两个 Secrets：`TCR_USERNAME`、`TCR_PASSWORD`，以及两个 Variables：

```text
TCR_REGISTRY=ccr.ccs.tencentyun.com
TCR_NAMESPACE=1999wiki_code
```

GHCR 使用工作流的 `GITHUB_TOKEN`，工作流发布作业声明 `packages: write`。现有 GHCR 包还必须允许此仓库的 Actions 访问；仅有 YAML 中的权限声明并不保证现有包可读写。

```powershell
gh workflow run publish-images.yml --repo DDomelette/1999Wiki --ref <发布分支>
gh run view <返回的运行ID> --repo DDomelette/1999Wiki
```

必须使用本次触发返回的运行 ID，并核对 `headSha` 等于冻结的完整 commit。不要仅按“最近一次运行”选择发布产物。

成功后下载精确产物：

```powershell
gh run download <运行ID> --repo DDomelette/1999Wiki `
  --name "release-$releaseTag" --dir <本机发布目录>

& 'D:\1999Wiki\.venv-windows\Scripts\python.exe' deploy/bin/release_manifest.py verify `
  --manifest <本机发布目录>/release-manifest.json `
  --commit $releaseCommit --registry tcr
```

该产物采用 `1999wiki.release/v2`，验证结果包含完整 commit 和两个带 digest 的镜像引用。保存清单原始字节与 SHA-256，传输到服务器后再次核对。

## 5. 备用路径：本机构建，上传腾讯云

本次实际采用该路径：Actions 的应用测试、镜像构建通过，但现有 GHCR 包拒绝 Actions token 访问，导致双仓库发布在写入腾讯云前终止。只读诊断已确认腾讯云登录和标签读取正常。

### 5.1 登录与构建

使用交互式密码输入登录腾讯云，或使用工具的 `--password-stdin`。不要将密码写入命令参数、日志、发布清单或 Git。CI 与服务器的凭据应保持一致，传入 Secrets 时避免额外换行。

```powershell
docker login ccr.ccs.tencentyun.com --username <腾讯云仓库用户名>

docker build --platform linux/amd64 --provenance=false `
  --label "org.opencontainers.image.revision=$releaseCommit" `
  --label org.opencontainers.image.source=https://github.com/DDomelette/1999Wiki `
  -f docker/Dockerfile.backend -t "${backendRepo}:$releaseTag" .

docker build --platform linux/amd64 --provenance=false `
  --label "org.opencontainers.image.revision=$releaseCommit" `
  --label org.opencontainers.image.source=https://github.com/DDomelette/1999Wiki `
  -f docker/Dockerfile.frontend -t "${frontendRepo}:$releaseTag" .
```

如果本机无法拉取 Node 构建镜像，可使用已验证的 Vite 生产产物打包，但必须先确认前端源码与冻结提交完全一致：

```powershell
git diff --quiet $releaseCommit -- frontend/react-app
# 非零退出码表示源码不同，必须停止。
```

将 `npm run build` 生成的 `dist/` 和同一提交的 `docker/frontend.Caddyfile` 复制到一个全新的独立上下文，使用与正式 Dockerfile 相同的 Caddy 运行阶段：

```dockerfile
FROM caddy:2.11.4-alpine
RUN addgroup -S caddy && adduser -S -D -H -G caddy caddy \
    && chown -R caddy:caddy /config /data
COPY dist /srv
COPY frontend.Caddyfile /etc/caddy/Caddyfile
USER caddy
EXPOSE 8080
```

仍应附加完整 commit 标签，指定 `linux/amd64`，并记录这种打包方式。不要把开发服务器、源码目录或 `node_modules` 当作前端运行镜像。

### 5.2 上传与固定摘要

上传前检查目标标签不存在；如已存在，停止并使用新的发布提交，不能覆盖旧标签。

```powershell
docker manifest inspect "${backendRepo}:$releaseTag"
docker manifest inspect "${frontendRepo}:$releaseTag"
# 只有明确的 manifest 不存在才可继续；鉴权或网络错误不能当作不存在。

docker push "${backendRepo}:$releaseTag"
docker push "${frontendRepo}:$releaseTag"

docker buildx imagetools inspect "${backendRepo}:$releaseTag"
docker buildx imagetools inspect "${frontendRepo}:$releaseTag"
```

记录仓库实际返回的 digest，正式部署使用：

```text
repository:sha-xxxxxxx@sha256:<64位摘要>
```

本次腾讯云单仓库清单采用 `1999wiki.tcr-release/v1`，如实记录 `ghcr.status=not_published`。它与标准双仓库 `1999wiki.release/v2` 不同，不能直接交给标准 `release_manifest.py verify` 或 GHCR backfill 工作流。

单仓库清单应至少记录完整 commit、发布标签、两份精确镜像引用和摘要、构建来源、通过的测试及未发布 GHCR 的原因。本次的清单还在安装时验证了 commit、标签、批准的仓库路径和摘要格式。

不能将 GHCR 权限错误冒充为“5 次网络失败后的延后镜像”；也不能生成实际上没有发布成功的 GHCR 镜像身份。

## 6. SSH 检查与准备候选版本

```powershell
$sshKey = 'C:\Users\HUAWEI\.ssh\tencent-1999wiki.pem'
ssh -i $sshKey -p 22 ubuntu@43.139.115.6
```

在服务器检查以下信息；受保护文件只查看发布状态，不打印应用凭据：

```bash
sudo cat /srv/1999wiki/deploy-state/active.env
docker ps --format '{{.Names}}|{{.Image}}|{{.Status}}'
df -h /srv/1999wiki
free -m
curl --fail --silent --show-error https://www.ddagent.cloud/health/ready
```

确认当前服务健康、四项基础设施健康、至少有 8 GiB 可用磁盘，选择与活动槽位相反的候选槽位。

通过私有临时目录传输发布清单，先核对 SHA-256，再安装到 `/srv/1999wiki/releases/<发布版本>/`。目录权限 `0700`，清单和槽位配置 `0600`，归 root 管理。不要把本机 `.env` 覆盖到生产环境。

以下为 root shell 中创建槽位文件的模板，变量必须来自已经核对的发布身份：

```bash
umask 077
RELEASE=sha-<7位commit>
COMMIT=<完整40位commit>
BACKEND=<后端tag@sha256:digest>
FRONTEND=<前端tag@sha256:digest>
install -d -m 0700 "/srv/1999wiki/releases/$RELEASE"

# green 候选；如果候选是 blue，改用 18100、18180，并改为 blue.env。
cat >"/srv/1999wiki/releases/$RELEASE/green.env" <<EOF
RELEASE_COMMIT=$COMMIT
BACKEND_IMAGE=$BACKEND
FRONTEND_IMAGE=$FRONTEND
BACKEND_PORT=18200
FRONTEND_PORT=18280
EOF
chmod 0600 "/srv/1999wiki/releases/$RELEASE/green.env"

docker pull "$BACKEND"
docker pull "$FRONTEND"
docker image inspect "$BACKEND" "$FRONTEND" --format '{{json .RepoDigests}}'
```

这次发布没有修改 `deploy/`，服务器运行脚本已逐文件核对；仅 `smoke-test.sh` 保留服务器上更严格的既有版本。以后如果修改运维文件，应先审查并传输同一发布提交的运行包，不在服务器克隆整个开发仓库。

## 7. 蓝绿部署与验收

候选槽位若仍是受保护的旧回滚目标，不能直接覆盖。先准备好新镜像、核对当前活动服务健康，再通过现有清理脚本退役那个已经停止的旧版本：

```bash
cd /srv/1999wiki/runtime-bundle
bash deploy/bin/cleanup.sh <旧回滚版本> <候选槽位> remove-<候选槽位>-<旧回滚版本>
```

该命令的版本、槽位和确认字符串必须严格匹配 `active.env` 记录；不能清理活动版本。退役后，立即继续发布新候选。

```bash
bash deploy/bin/preflight.sh <新版本> <候选槽位>

env PUBLIC_BASE_URL=https://www.ddagent.cloud \
    SMOKE_RAG_QUESTION='请介绍槲寄生' \
    bash deploy/bin/deploy.sh <新版本> <候选槽位>
```

从普通 `ubuntu` SSH 会话执行时，需要 `sudo -n` 或进入已授权的 root shell。运维脚本需要读取 root 所有的配置与状态。

现有脚本负责操作锁、配置快照、拉取精确镜像、启动候选容器、健康等待、冒烟测试、Caddy 原子切换、活动状态提交及停止旧槽位。

预检会验证 RAG 闭包和权限。本次应为 **11 个文件、222,789,868 bytes**；目录 `0755`、选中文件 `0644`。不要为了通过预检而跳过哈希校验或宽泛修改所有目录权限。

冒烟测试包含：首页及带哈希的静态资源、完整 readiness、Wiki 列表和详情、同步问答、SSE 和公网媒体读取。服务器现有加强版还要求至少两个非空 token、唯一的末尾 `done`，以及流式可见答案和 `done.answer` 一致。

`PUBLIC_BASE_URL` 使用实际 HTTPS 域名，避免 HTTP 重定向、Host 路由或证书差异影响媒体和公网校验。

切换后继续核对：

```bash
sudo cat /srv/1999wiki/deploy-state/active.env
sudo cat /etc/caddy/active-upstream.caddy
docker ps --format '{{.Names}}|{{.Image}}|{{.Status}}'
curl --fail --silent --show-error https://www.ddagent.cloud/health/ready
```

新前后端应 `healthy` 且 `RestartCount=0`；旧活动版本应成为 `PREVIOUS_*` 回滚目标，保留其镜像和快照。公网首页及 readiness 应 HTTP 200，TLS 校验正常。

最后在浏览器检查桌面、手机、Wiki 懒加载和真实聊天。页面有背景视频，自动化验收使用 `domcontentloaded` 加目标元素可见等待；持续媒体请求可能让 `networkidle` 一直不满足。

## 8. 失败处理与回滚

如果在切换前失败，先确认原活动槽位仍健康，保留失败日志，检查候选状态，修复后再重试。不要直接重启整套基础设施。

如果切换后的公网验证失败，使用现有回滚脚本恢复受保护的上一个版本：

```bash
sudo env \
  PUBLIC_BASE_URL=https://www.ddagent.cloud \
  SMOKE_RAG_QUESTION='请介绍槲寄生' \
  bash /srv/1999wiki/runtime-bundle/deploy/bin/rollback.sh
```

随后重新核对活动状态、Caddy 上游、容器健康及公网访问。回滚使用旧的发布和应用配置快照，不迁移或删除持久数据。

禁止将 `docker compose down -v`、无范围的 `docker system prune -a`、数据库目录删除或全量覆盖配置用于应用回滚。

## 9. 本次排障留下的要点

| 问题 | 原因与处理 |
| --- | --- |
| 历史语料证据测试缺少 Git 对象 | Python CI 的 checkout 改为 `fetch-depth: 0`。 |
| Linux 上 Windows 创建标志断言失败 | POSIX 检查零值；Windows 检查实际 Windows 标志。 |
| 旧 story baseline 依赖未提交的本地评测文件 | 纳入工作区既有的退役工具、测试和评测文件清理。 |
| 后端镜像导入缺少 `build.artifact_writer` | 将 BM25 探针指纹提取到轻量运行时模块，保持算法不变，不把整个离线构建器装进生产镜像。 |
| Skopeo 在登录前解析失败 | 凭据文件必须初始化为有效的 `{"auths":{}}` JSON，不能是空文件；权限保持 `0600`。 |
| Actions 登录 GHCR 成功，但包读取被拒绝 | 登录成功不等于包权限足够；只读诊断分别验证了两家仓库、已有标签和新标签。此次改用本机到腾讯云的备用发布流程。 |
| 本机无法获取 Node 基础镜像 token | 使用源码一致、已通过测试的 Vite `dist` 加正式 Caddy 运行阶段打包，并在清单中记录。 |
| 浏览器 `networkidle` 超时 | 背景媒体请求持续，改为 DOM 和实际 UI 条件等待。 |

GHCR 包权限仍需单独补齐后才能恢复 Actions 的完整双仓库发布。不要直接重跑本次发布去覆盖已经存在的 `sha-d214556` 标签；后续修复使用新的发布提交。

## 10. 每次发布要保存的记录

至少记录：完整 commit、分支、发布标签、构建和测试结果、工作流运行 ID、真实镜像摘要、发布清单 SHA-256、活动与回滚槽位、公网验收和回滚命令。

非敏感运行产物可以保存在本机 `.local/<发布目录>/`；正式发布说明写入 `docs/`。密钥、密码、生产 `.env` 和完整 Docker 环境变量不能进入这些记录。
