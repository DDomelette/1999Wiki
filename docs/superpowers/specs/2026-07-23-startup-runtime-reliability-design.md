# 1999Wiki 一键启动与运行时可靠性设计

日期：2026-07-23

## 1. 背景与目标

项目根目录的 `start.ps1` 当前通过 `conda run -n langchain` 定位 Python，因此实际使用了 `D:\Anaconda32024\envs\LangChain\python.exe`，与目标环境 `1999wiki` 不一致。当前机器上的 Conda 插件还存在 DLL 加载异常，使 `conda run` 不是可靠的启动前置条件。

启动器在应用启动前执行 Huiji provenance 验证。验证器创建 `MilvusClient` 时没有设置连接超时；当 Milvus 容器已经启动但尚未健康，或者 Docker 端口转发短暂未就绪时，gRPC 会长时间停留在 Connect。此时按 Ctrl+C 会由 Python 输出完整 `KeyboardInterrupt` traceback。

本次改动的目标是：

- 固定使用 `D:\Anaconda32024\envs\1999wiki\python.exe`。
- 让 PowerShell 一键启动器负责启动项目 Compose 基础设施并等待健康。
- 让 Milvus 连接失败在有限时间内给出明确、可操作的错误。
- 让启动任意阶段的 Ctrl+C 都能安静退出并清理已启动的应用子进程。
- 在启动前验证 Python 与前端依赖，准确报告缺失或版本不符。
- 保持 `start.ps1`、`start.bat` 和 README 的用户可见行为一致。

## 2. 已确认现状

- `1999wiki` 环境存在，解释器为 `D:\Anaconda32024\envs\1999wiki\python.exe`，Python 3.11.15。
- 当前 Milvus、MinIO、etcd、MySQL 容器健康；`1999wiki` 环境连接 Milvus 约 32 ms，旧 `LangChain` 环境约 68 ms。
- 使用带 5 秒连接超时的只读运行时验证结果为 `status=pass`，无 provenance issue。
- `pip check` 未发现已安装包之间的依赖损坏，关键模块均可导入。
- `requirements.txt` 中只有一项与环境不一致：要求 `markdown-it-py==2.2.0`，实际安装 4.2.0。
- React `node_modules` 已安装，`npm ls --depth=0` 通过。

因此，已观察到的 traceback 不表示 Milvus collection 损坏；它表示报错当时客户端正在等待 gRPC Connect，且代码没有超时和安静中断处理。

## 3. 方案选择

### 3.1 采用方案

采用“基础设施预启动 + 健康等待 + 有界 provenance 验证”的方案：

1. 校验固定 Python 解释器。
2. 校验 Python 依赖。
3. 调用项目 Compose 启动基础设施。
4. 等待必需容器健康。
5. 执行带连接超时的 provenance 验证。
6. 启动后端，等待应用健康。
7. 启动各前端。
8. Ctrl+C 时只清理本次启动器创建的应用进程。

### 3.2 未采用方案

- 仅替换解释器：无法处理基础设施启动顺序，仍不是真正的一键启动。
- 新建常驻服务管理器：引入额外进程、状态文件和维护成本，超出本次需要。

## 4. 组件设计

### 4.1 Python 解释器解析

`start.ps1` 使用固定路径：

```text
D:\Anaconda32024\envs\1999wiki\python.exe
```

启动时先验证文件存在并执行轻量版本检查。找不到或无法执行时立即退出，错误信息包含期望路径与修复建议。启动链路不再依赖 `conda activate` 或 `conda run`。

`start.bat` 使用相同路径和失败语义。

### 4.2 依赖预检

新增一个小型、只读的 Python 依赖检查脚本，读取 `requirements.txt`，使用已安装 distribution 元数据检查：

- 包是否安装；
- 固定版本或版本范围是否满足；
- `pip check` 是否通过。

检查器输出紧凑的缺失/版本不符列表，并以非零状态退出。启动器不在每次启动时自动安装或升级包，避免无意修改环境；修复命令明确指向固定解释器的 `python -m pip install -r requirements.txt`。

实施时先将 `1999wiki` 环境中的 `markdown-it-py` 对齐到 `requirements.txt` 指定的 2.2.0，然后再次执行依赖检查与关键模块导入测试。

React 侧保留首次缺少 `node_modules` 时执行 `npm install` 的现有行为；已有目录时运行快速的顶层依赖检查，失败则提示重新安装。

### 4.3 Compose 基础设施管理

启动器使用：

```text
docker compose -f infra/milvus/docker-compose.yml up -d
```

在调用前检查 Docker CLI 和 Docker daemon。Compose 启动后，轮询以下服务：

- `milvus-main-etcd`
- `milvus-main-minio`
- `milvus-main-standalone`
- `reverse1999-main-mysql`

容器必须处于 running，定义了 healthcheck 的容器还必须达到 healthy。总等待上限为 180 秒；期间显示当前未就绪服务，超时后显示 `docker compose ps` 和查看日志的命令。

这些容器保存长期项目数据。退出启动器时不执行 `docker compose down` 或 `stop`，也不删除 volume。

### 4.4 Provenance 验证

`scripts/verify_huiji_runtime.py` 创建 `MilvusClient` 时设置显式连接超时，默认 10 秒。连接或验证失败仍保持 fail-closed：后端和前端均不启动。

普通异常输出安全、简短的错误类型和操作提示，不泄露凭据。`KeyboardInterrupt` 单独转换为退出码 130，并输出一行“验证已取消”，不显示 traceback。

`src/huiji_rag/provenance.py` 内部默认客户端使用相同连接超时，避免其他直接调用路径重新引入无限等待。

### 4.5 启动与关停边界

`start.ps1` 的外层 `try/finally` 覆盖依赖检查、Compose 等待、provenance、后端和前端启动全过程。

启动器维护本次创建的应用进程集合，包括 FastAPI、Streamlit、Gradio 和 Vite。退出或失败时只终止该集合中的仍存活进程，不按宽泛进程名清理，也不停止 Docker 基础设施。

如果 Ctrl+C 发生在 Python verifier 运行期间，验证器安静返回 130，PowerShell 显示取消信息并进入 finally。若发生在健康等待或主循环，同样进入 finally。

## 5. 错误处理与用户输出

启动输出按以下阶段显示：

```text
[step] 使用解释器
[step] 检查 Python 依赖
[step] 启动并等待基础设施
[step] 验证 Huiji RAG provenance
[step] 启动并等待后端
[step] 启动前端
```

失败信息必须区分：

- 固定解释器不存在或不可执行；
- Python 依赖缺失/版本不符；
- Docker CLI 或 daemon 不可用；
- 某个 Compose 服务未健康；
- Milvus 连接超时；
- provenance 内容不一致；
- 应用端口被占用；
- 后端健康检查超时；
- 用户主动取消。

非交互调用不使用无条件 `Read-Host` 阻塞；交互窗口中的最终错误信息保持可读。

## 6. 测试与验收

### 6.1 自动化测试

- 扩展 `tests/test_start_scripts.py`，验证两个启动器使用 `1999wiki` 固定解释器、在 provenance 前启动并等待 Compose、保持 fail-closed，并包含全流程清理边界。
- 为依赖检查脚本增加缺包、版本匹配、版本不符和 `pip check` 失败测试。
- 为 runtime verifier 增加 Milvus 超时参数测试、连接错误测试和 `KeyboardInterrupt` 返回 130 测试。
- 运行现有 provenance、配置、后端门禁和启动脚本测试。
- React 执行 `npm ls --depth=0`，必要时执行现有前端测试。

### 6.2 手工验收

1. 停止项目 Compose 服务后运行 `start.ps1`，确认其自动启动基础设施并等待 healthy。
2. 验证四个应用端口 8000、8501、7860、5173 可访问。
3. 确认 `/health` 返回 `status=ok` 和 `provenance_status=pass`。
4. 在启动等待阶段按 Ctrl+C，确认没有 Python traceback，且已启动的应用子进程被清理。
5. 退出正常运行的启动器，确认应用子进程停止，但 Milvus、MinIO、etcd、MySQL 保持运行。
6. 模拟 Milvus 不健康，确认在有界时间内失败并给出具体诊断。

## 7. 范围边界

本次不会重建、覆盖、删除或切换任何 Milvus collection，不修改 provenance baseline，不删除 Docker volume，也不改变业务检索逻辑。只调整本地启动编排、依赖验证、连接超时、取消行为和对应文档测试。
