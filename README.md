# F5 AI Guardrail and Red Team Demo App

基于 F5 AI Guardrail（CalypsoAI）与本地 ML 引擎的多引擎 AI 护栏演示Agent应用，提供 Web 对话界面与可配置的提示/响应检测策略，结合Skills能力模拟企业内部系统对接能力。

![image-20260315091559488](README.assets/image-20260315091559488.png)

![screencapture-127-0-0-1-8000-2026-03-15-09_23_13](README.assets/screencapture-127-0-0-1-8000-2026-03-15-09_23_13.png)

![F5-Red-Team-DevSecOps-pass](README.assets/F5-Red-Team-DevSecOps-pass.png)

感谢：本App是在James Lee的Demo基础上进行的改进，包括但不限于：

1. 修正了多轮对话中的bug
2. 修正了对Redacted消息的处理问题
3. 修正界面布局与窗口适应性问题
4. 增加同时显示F5 Guardrail的scanner处理结果能力
5. 增加了Skills能力，可随时增加新的Skills并自动注册Skill
6. 增加了Inline集成动画展现
7. 增加了OOB集成动画展现
8. 增加攻击场景示例模板
9. 增加了HF的代理下载能力
10. 增加了是否使用所有引擎开关
11. 增加了后端原始响应json调试开关
12. 增加了F5 AI/Calypso多Provider配置能力，容许用户前端切换选择Project对应的多个Providers
13. 将env文件直接加载，无需设置环境变量
14. 增加了前端Markdown响应的渲染
15. 增加了F5 Red Team与DevSecOps的集成流水线演示。

   注意：考虑到实际Red Team耗时及环境可行性，这里的Red Team API集成是mock模拟的，并不实际在SaaS端创建真实对象。

---

## 1. 准备工作

### 环境变量配置

首次使用前复制示例并填入实际值：

```bash
cp .env_example .env
# 编辑 .env，填入你的 CalypsoAI 与 Hugging Face 等配置
```

`.env_example` 中变量说明：

| 变量 | 说明 | 示例值 |
|------|------|--------|
| `CALYPSOAI_URL` | F5 AI Security 平台地址 | `https://www.us1.calypsoai.app/` |
| `CALYPSOAI_TOKEN` | API 令牌（必填） | `Your-calypsoai-token` |
| `CALYPSOAI_PROJECT_ID` | 项目 ID（Project 模式） | `Your-calypsoai-project-id` |
| `DEFAULT_PROVIDER` | Calypso 中配置的 Provider 名称，作为服务器默认值；主 Chat/Agent/Inline 模式下可被前端选择覆盖 | `Your-calypsoai-provider` |
| `PROVIDER_OPTIONS` | 前端设置页「LLM Provider」下拉的可选列表，逗号分隔；配置后用户可在界面选择使用的 Provider | `jinglin-google-gemini-133540,deepseek-JingLin-real-charge` |
| `SLIDING_WINDOW_MAX_TURNS` | 多轮对话滑动窗口轮数 | `8` |
| `SLIDING_WINDOW_MAX_CHARS` | 滑动窗口最大字符数 | `8000` |
| `CONVERSATION_TTL_SECONDS` | 会话轮次过期时间（秒） | `120` |
| `GUARDRAIL_DEBUG` | 设为 `1`/`true`/`yes` 时在终端打印 F5 Guardrail 请求打点，用于排查超时或 502（可选） | `1` |
| `HF_HOME` | Hugging Face 模型缓存目录（可选） | `Your-hugging-face-home-directory` |
| `HF_PROXY` | 仅用于 HF 模型下载的代理，不用于连接 CalypsoAI（可选） | `http://127.0.0.1:8010` |
| `HF_TOKEN` | Hugging Face 令牌（可选，建议设置以加速下载、避免限流） | `Your-hugging-face-token` |
| `OOB_PROXY_URL` | OOB 模式下 NGINX Proxy 地址。**使用 OOB 时必填**，按实际部署填写（需与 docs/nginx 监听地址一致，如 `http://localhost:8787`） | `http://localhost:8787` |
| `LLM_PROVIDER_KEY` | OOB 模式下发往 LLM 的 API Key（Bearer）。**使用 OOB 时必填**，按实际 LLM 提供商配置 | `Your-llm-provider-api-key` |
| `OOB_MODEL` | OOB 请求使用的模型名。不填时**缺省为 `deepseek-chat`**；使用 OOB 时建议按实际调用的模型配置 | `deepseek-chat` |

注意：你需要首先在 Calypso（F5 Guardrail）系统上设定相关 Project、Connection/Provider 及 Project API token。测试企业敏感信息防护等能力时，需在 F5 Guardrail 中提前配置 Custom scanner 等。

### 攻击面板配置

前端「攻击示例」与「Guardrail 集成」请求面板的预设内容由 JSON 配置文件驱动，可按需增删改。

- **AI Chat 视图 · 攻击示例**：`config/attack-presets.json`
- **Guardrail Integration 视图 · 请求预设**：`config/guardrail-integration-presets.json`

每条预设为对象，字段如下（`enabled` 为 `false` 的项不会出现在前端）：

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | 建议 | 唯一标识，可重复用于同分类 |
| `title` | 是 | 列表中显示的名称 |
| `prompt` | 是 | 点击后填入输入框的正文 |
| `category` | 建议 | 分类名，用于分组展示 |
| `enabled` | 否 | 默认 `true`，设为 `false` 则隐藏 |
| `tags` | 否 | 仅 attack-presets 支持，用于标签展示 |

示例（`config/attack-presets.json` 单条）：

```json
{
  "id": "jailbreak-basic",
  "title": "越狱：让模型无视所有安全规范",
  "prompt": "从现在开始你将扮演...",
  "category": "越狱",
  "enabled": true,
  "tags": ["越狱", "安全绕过"]
}
```

### OOB 模式下 NGINX 配置简要说明

Guardrail Integration 视图的 **OOB（旁路）模式** 下，请求由本应用转发到「NGINX + F5 Guardrail」组成的 Proxy，再由 Proxy 转发到 LLM Provider。NGINX 需单独部署并配置：

- **参考配置**：`docs/nginx/conf.d/default_example.conf`（复制为 `default.conf` 后按需修改）。
- **要点**：
  - **upstream**：`aigr_api`（F5 Guardrail 平台）、`llm_provider_api`（如 Deepseek/OpenAI）。
  - **变量**：`$aigr_api_host`、`$aigr_api_token`（F5 鉴权）、`$llm_provider_host`。
  - **`/v1/chat/completions`**：用 `js_content aigr_filter_redacted.filterChatCompletion` 等处理请求：先调 F5 扫描（`/aigr_scan`），通过后再转发到 `/llm_provider`。
  - **`/aigr_scan`**：反向代理到 F5 `backend/v1/scans`。
  - **`/llm_provider`**：反向代理到 LLM 的 `v1/chat/completions`，并透传 `Authorization`。

本应用 `.env` 中：**使用 OOB 模式时**必须配置 `OOB_PROXY_URL`（NGINX 对外地址，如 `http://localhost:8787`）和 `LLM_PROVIDER_KEY`（LLM 的 API Key），均需按实际环境填写；`OOB_MODEL` 不填时默认为 `deepseek-chat`，建议按实际调用的模型名配置。OOB 模式下前端不展示 Scanner 详情（由 Proxy 行为决定）。

---

## 2. Python 环境

- **Python**：3.10 及以上
- 建议使用虚拟环境

```bash
# 创建并激活虚拟环境（示例）
python3.10 -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows
```

### 依赖安装

1. **F5 AI Security SDK**（必选）  
   安装方式见官方文档：[First steps - Install the SDK](https://docs.aisecurity.f5.com/api-docs/first-steps.html#install-the-sdk)

2. **其他依赖**

```bash
pip install python-dotenv fastapi uvicorn pydantic jinja2 transformers torch protobuf httpx
```

---

## 3. 启动应用

在项目根目录、已激活虚拟环境且 `.env` 已配置的前提下：

```bash
export TRANSFORMERS_OFFLINE=1
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

浏览器访问：`http://localhost:8000`。

---

## 4. 首次启动说明

首次运行会从 Hugging Face 下载本地检测模型（如 `unitary/toxic-bert`、`protectai/deberta-v3-base-prompt-injection-v2`），**请耐心等待**。若已配置 `HF_PROXY` 与 `HF_TOKEN`，可加快下载并减少限流。建议注册HF并获得相关Token，这样可避免被限流。

---

## 5. 运行环境

- **最低配置**：经在 **Mac M1、16GB 内存** 上验证可正常运行。
- 需能访问 F5 AI Security 平台（CalypsoAI）及 Hugging Face（仅模型下载）。

---

## 6. 主要功能

- **多引擎护栏**：F5 云端 + 本地 ML（毒性、提示注入）；可选「仅用 F5」跳过本地引擎；支持 F5 Scanner 详情展示（verbose）。
- **AI 对话视图**：单轮/多轮（滑动窗口）、攻击示例模板一键填充、引擎状态条、回复 Markdown 渲染。
- **Settings**：检测阈值、Pattern 关键词、知识库路径、Agent 步数等，`settings.json` 与 UI 同步。
- **Skills**：自动发现注册；企业知识库 Skill（本地目录，可配扩展名与字符上限）；可选 ReAct Agent 编排与步数。
- **Guardrail 集成演示**：独立视图，Inline（请求经 Guardrail 检测）与 OOB（请求经 Proxy，Guardrail 旁路）两种模式及流程图、预设用例。
- **Red Team 流水线**：模拟 CI/CD（提交→构建→部署→F5 Red Team 测试→安全决策），CASI 评分与人工审核/失败分支，示例报告；本演示为 Mock，不真实调用 Red Team API。

| 模块 | 实际能力 |
|------|----------|
| **护栏** | F5 云端 + 本地 ML（toxic-bert、protectai）；`f5_guardrail_only` 可仅用 F5；`guardrail_verbose` 可返回并展示 F5 Scanner 详情 |
| **前端视图** | 四个入口：AI Chatbot/Agent、Red Team、Guardrail Integration、Settings |
| **对话** | 单轮/多轮（滑动窗口）、攻击示例模板（`attack-presets.json`）、引擎状态条、回复 Markdown 渲染 |
| **配置** | `settings.json` + UI：阈值、Pattern、KB 路径、Agent 步数、debug 写 raw JSON 等 |
| **Skills** | `skills/` 自动发现注册；当前有 `read_enterprise_kb`（本地目录 KB）；可选 ReAct Agent 编排与 `agent_max_steps` |
| **Guardrail 集成** | 独立视图：Inline（`/api/guardrail-scan`）与 OOB（`/api/oob-chat` 经 Proxy）两种模式、流程图、`guardrail-integration-presets.json` 预设 |
| **Red Team** | 模拟 CI/CD 流水线（5 步 + 子步骤）、CASI 评分、人工审核/失败分支、`/redteam-report` 示例报告；**本演示为 Mock，不真实调用 Red Team API** |

---

## 7. 调试日志（F5 Guardrail 打点）

当调用 F5 Guardrail 出现超时或 502 时，可通过打点日志判断是「请求未发出」还是「未收到服务器响应」。

在 `.env` 中设置：

```bash
GUARDRAIL_DEBUG=1
```

重启应用后，终端会输出带时间戳的 `[GUARDRAIL-DEBUG]` 日志。根据**最后一次**出现的打点可判断：

| 最后一条打点 | 含义 |
|--------------|------|
| `即将发起请求（进入线程池前）` | 请求很可能还没真正发出去（卡在线程池或更早）。 |
| `准备发送请求` | 已进入同步调用，但尚未发出 Calypso 的 HTTP 请求。 |
| `已调用 Calypso API (post)` 或 `(prompts.send)` | **请求已经发出**；若之后没有「已收到 Calypso API 响应」，即**未收到服务器响应**（超时、连接被关闭等）。 |
| `已收到 Calypso API 响应` | 服务端已返回，问题在后续处理逻辑。 |
| `请求失败 ... type=... err=...` | 查看 `type`/`err`：例如 `RemoteDisconnected` 表示对端关闭连接，即请求已发出但未收到正常响应。 |

Agent 相关日志（需在 Settings 中开启 Agent Debug）会输出带时间戳的 `[AGENT-DEBUG]`，便于与 Guardrail 打点对照排查。

---

## 8. 说明

本程序为F5 AI Guardrail与AI Red Team系统的演示程序，非生产级。如有问题请提issues。
