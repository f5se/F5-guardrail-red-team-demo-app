# Agentic Security · LangGraph 运行时模块

本目录实现 **Agentic Security** 视图所用的 **LangGraph** 状态机与 Mock 业务工具，由项目根目录的 FastAPI 应用加载（**实际 HTTP 入口不在此文件的 `main.py`**）。

## 图编排（概要）

```
supervisor_plan → research ⇄ … → action ⇄ … → finalize → legal_counsel → END
```

- **Supervisor**：`plan`（JSON 目标拆分）、`finalize`（面向用户的汇总；法律分析不在此步写）。
- **Research**：多轮取证，可调用检索类工具。
- **Action**：多轮执行，可调用采购/通知等 Mock 工具，直至产出 `final`。
- **Legal Counsel**：在 Supervisor 汇总之后执行；`legal_review`（≤50 字中文法律风险一句简评）+ 两条配置驱动的纯对话轮次（`simple_dialog`，主题来自 `legal_counsel` 配置）。

条件边与轮次上限以 `graph.py` 为准。

## 文件说明

| 文件 | 作用 |
|------|------|
| `graph.py` | `StateGraph` 节点、路由、`build_langgraph_runner(...)` 导出；trace 行含 `agent_name`、`action_type`、`guardrail_outcome` 等。 |
| `tools.py` | Mock 工具实现、`tools_catalog`、从 **`config/agentic-tools-config.json`** 读取/合并的 `get_tool_config` / `save_tool_config`（含 `legal_counsel` 附加话题等）。 |
| `llm_client.py` | OpenAI-compatible 调用与 `x-cai-metadata-session-id` 头等的**参考实现**；生产环境 LLM 调用由根目录 `main.py` 中 `_agentic_openai_chat` 注入。 |
| `main.py` | 仅占位入口（`run()` 提示使用根服务）；不作为 uvicorn 目标。 |
| `__init__.py` | 包标记。 |

## 与根项目的衔接

- **运行**：`POST /api/agentic/run`、`GET /api/agentic/run-trace`、`GET|POST /api/agentic/tool-config`（见根目录 `main.py`）。
- **前端**：`Agentic Security` 视图、流程可视化、Agentic Tool Config 面板。
- **风险模板**：根目录 `config/agentic-risk-templates.json`（与本包并行维护，由 API/UI 使用）。

若要将本包抽离为独立库，优先以 `graph.py` + `tools.py` 的公共接口为准，并替换根目录注入的 `llm_call` / `trace_logger`。
