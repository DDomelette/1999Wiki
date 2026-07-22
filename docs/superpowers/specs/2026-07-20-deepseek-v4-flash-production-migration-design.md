# DeepSeek V4 Flash 生产 RAG 迁移设计

> 日期：2026-07-20
>
> 状态：用户已批准

## 目标

在不改变 RAG 问答链路职责和传输语义的前提下，将生产 RAG 使用的 DeepSeek 兼容别名迁移到官方 V4 模型名，避免 `deepseek-chat` 停用造成服务中断。

## 范围

- 将生产 LLM base URL 从 `https://api.deepseek.com/v1` 改为官方写法 `https://api.deepseek.com`。
- 将生产模型从 `deepseek-chat` 改为 `deepseek-v4-flash`。
- 在生产 `ChatOpenAI` 请求中显式传递 `thinking.type=disabled`，保持原 `deepseek-chat` 的非思考语义。
- planner、grounded answer、自由补充和引用修复继续共享生产 LLM 配置。
- 增加配置加载与客户端构造测试。
- 更新项目理解文档中的当前模型说明。

## 非目标

- 不修改 `src/rag_eval/judge.py`。
- 不修改 `RAG_EVAL_JUDGE_*` 环境变量、评测运行清单或历史评测产物。
- 不启用 `reasoning_effort`；该参数只适用于思考模式。
- 不改成 DeepSeek 原生流式输出，不改变当前“完整生成、引用校验、冻结后再切片”的 SSE 语义。
- 不在本次迁移中拆分 planner、answer 和 citation repair 的模型配置。

## 配置与数据流

`config/settings.yaml` 的 `llm` 节新增显式 `thinking: "disabled"`。`config/config.py` 将其加载到 `LLMCfg`，并只接受 `enabled` 或 `disabled`，非法值在启动加载配置时失败。

`RAGChain._build_llm()` 继续为 planner 和 answer 创建独立客户端，但二者都向 `ChatOpenAI` 传递：

```python
extra_body={"thinking": {"type": cfg.llm.thinking}}
```

因此 planner 的 `temperature=0` 与 answer 的既有 temperature 行为继续在非思考模式下有效。Judge 使用独立构造路径，不读取该参数，不受影响。

## 失败处理

- 配置缺少 `thinking` 时默认使用 `disabled`，避免旧测试 fixture 或本地覆盖突然进入思考模式。
- 配置值不是 `enabled`/`disabled` 时抛出 `ValueError`，阻止以不确定模式启动生产链路。
- DeepSeek 连接、鉴权和模型错误继续沿用现有问答链路的错误处理，不在本次修改中扩展。

## 验收条件

1. `get_config().llm.base_url == "https://api.deepseek.com"`。
2. `get_config().llm.model == "deepseek-v4-flash"`。
3. `get_config().llm.thinking == "disabled"`。
4. planner 与 answer 两次 `ChatOpenAI` 构造均携带 `extra_body={"thinking": {"type": "disabled"}}`。
5. Judge 文件和评测配置无本次差异。
6. 配置测试、生产客户端构造测试以及现有 RAG 聚焦测试通过。
