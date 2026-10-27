# 2026-10-27 UI 发布记录

状态：已上线。2026-10-27 22:18:46（Asia/Shanghai）切换到 green，部署后公网与真实浏览器验收通过。

- 网站：https://www.ddagent.cloud
- 服务器：`ubuntu@43.139.115.6:22`
- SSH 私钥位置：`C:\Users\HUAWEI\.ssh\tencent-1999wiki.pem`
- 发布分支：`codex/ui-release-20261027`
- 源码提交：`d214556a381c9b5a8ef5d525b3b5b0678db232b4`
- 发布版本：`sha-d214556`
- GitHub Actions：https://github.com/DDomelette/1999Wiki/actions/runs/40514955622
- 镜像仓库：`ccr.ccs.tencentyun.com/1999wiki_code`
- 发布前活动版本：`sha-345fa54`，blue 槽位。
- 本次目标：green 槽位，后端端口 `18200`，前端端口 `18280`。

操作手册见 [Docker 部署手册](../../deployment.md)。

## 实际发布方式与镜像身份

GitHub Actions 的应用测试和两个镜像构建均通过，但发布作业因现有 GHCR 包拒绝 Actions token 读取而失败。本次按历史备用流程，从本机构建并上传腾讯云，然后使用原有蓝绿部署脚本上线。

服务器与本机发布清单 SHA-256 一致：`a3cef3877a79592b8c70a38f43e8fa8ef9c025ddba04d61320f78403f51204ab`。

| 组件 | 腾讯云镜像摘要 |
| --- | --- |
| Backend | `sha256:41cb9dafb7d2ae5d04151f87ff41a5610ff2e08126e09cc608521beaea9c3976` |
| Frontend | `sha256:cfc4822c39537bdba2232c0ea80822586924165ac67303186746a228e592d541` |

两者标签均为 `sha-d214556`，平台均为 `linux/amd64`，镜像 revision 标签均为完整源码提交。服务器使用 `tag@sha256:digest` 引用。

本次清单采用如实记录腾讯云单仓库发布的 `1999wiki.tcr-release/v1`，GHCR 状态为 `not_published`，不是标准双仓库 v2 清单，也不伪称网络延后。只读诊断运行：https://github.com/DDomelette/1999Wiki/actions/runs/40518092638 。

本机拉取 Node 基础镜像出现网络超时，因此前端使用已通过测试、生产构建和源码一致性比较的 Vite `dist`，加正式 Dockerfile 相同的 Caddy 运行阶段打包。

## 发布范围

纳入现有首页、聊天页、移动端布局、Wiki 懒加载和 SSE 完成处理的前端改动。
未纳入其他爬虫、离线处理、Windows 本地环境修复和文档整理改动。

为恢复原有发布流程，同时修复了：

1. Python CI 拉取完整 Git 历史，满足历史语料证据测试。
2. 进程标志测试在 POSIX 上检查零值，在 Windows 上检查对应标志。
3. 纳入工作区中已经删除的旧 story baseline 工具、测试和评测文件。
4. 将 BM25 探针指纹函数提取到轻量运行时模块，避免生产镜像导入离线构建器；探针内容与哈希算法保持一致。
5. Skopeo 凭据文件初始化为有效 JSON，修复原流程在登录阶段立即退出的问题。

这些发布修复也已同步到原工作区；用户原有未提交的改动保留。

## 验证记录

- 本地前端：329 项测试通过，生产构建通过。
- 桌面及手机 UI：首轮 13 项通过、4 项按平台跳过；1 项桌面吸附出现 3px 偏差，随后单独复查连续 4 次通过。
- 发布检查修复定向测试：92 项通过。
- 容器依赖修复定向测试：121 项通过。
- Linux 后端镜像在本机成功构建，容器内后端导入成功且未加载离线构建器。
- 注册表传输与发布检查：129 项通过；真实 Skopeo 已确认凭据 JSON 解析通过。
- 镜像导入修复后的完整 CI：Python 2621 项通过、3 项跳过，前端 329 项通过；前后端镜像均成功构建。
- 最终源码提交的 CI：Python 2621 项通过、3 项跳过；前端 329 项通过，生产构建通过。整体发布作业的 GHCR 权限失败不能记为 CI 发布成功。
- 腾讯云镜像上传成功，仓库摘要与服务器拉取后的 `RepoDigests` 一致。
- 服务器预检通过，RAG 11 个文件与 222,789,868 bytes 内容及权限均通过验证。
- 候选槽位两轮冒烟测试通过，包含同步问答、SSE 最终答案一致性、Wiki 和媒体读取。
- 切换后的前后端均 `healthy`、重启次数 `0`；四项基础设施均健康。
- 两个公网域名首页均 HTTP 200、TLS 校验正常；readiness 全部通过。
- 公网浏览器验收：新资源 `/assets/index-CT1oSnog.js`，桌面、手机和 Wiki 通过；真实问答收到 1041 个 token 并以 `done` 正常结束；脚本异常为零，手机横向溢出为零。
- 浏览器截图使用 DOM 与元素可见等待，并跳过字体就绪等待；页面持续媒体请求和字体下载会延迟自动化工具默认的等待条件。

## 部署与回滚

沿用 [生产部署手册](../production-deployment-runbook.md) 的不可变镜像、受保护配置快照和蓝绿切换流程。
服务器只运行容器，不克隆源码，不构建镜像，不迁移数据库或 RAG 数据。
保留服务器现有加强版 `smoke-test.sh`：除首页、Wiki、问答和媒体外，还校验 SSE token、终止事件与最终答案一致。

当前活动版本为 green 的 `sha-d214556`，`sha-345fa54` 已成为受保护的 blue 回滚目标。复用 green 前，已通过现有清理脚本退役停止的 `sha-68e531f`，保留原发布记录与快照。需要回滚时，在服务器上运行：

```bash
sudo env \
  PUBLIC_BASE_URL=https://www.ddagent.cloud \
  SMOKE_RAG_QUESTION='请介绍槲寄生' \
  bash /srv/1999wiki/runtime-bundle/deploy/bin/rollback.sh
```

本机发布产物、操作脚本与验收结果位于 `.local/ui-release-20261027/`；该目录不提交 Git。
服务器发布目录为 `/srv/1999wiki/releases/sha-d214556/`。活动快照位于 `/srv/1999wiki/deploy-state/snapshots/sha-d214556/green/`。

GHCR 包权限仍需补齐才能恢复原 Actions 双仓库发布；本次腾讯云镜像及线上服务已完成部署和验收。后续不要覆盖 `sha-d214556`，应创建新发布提交。
