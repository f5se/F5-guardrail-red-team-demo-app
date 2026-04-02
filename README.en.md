# F5 AI Guardrail and Red Team Demo App

A multi-engine AI guardrail demo Agent application based on F5 AI Guardrail (CalypsoAI) and local ML engines. It provides a web chat interface with configurable prompt/response detection policies and integrates Skills to simulate enterprise system integration.

![image-20260315091559488](README.assets/image-20260315091559488.png)

![screencapture-127-0-0-1-8000-2026-03-15-09_21_04](README.assets/screencapture-127-0-0-1-8000-2026-03-15-09_21_04.png)

![F5-Red-Team-DevSecOps-failure](README.assets/F5-Red-Team-DevSecOps-failure.png)

**Credits:** This app is an improvement on James Lee's demo, including but not limited to:

1. Fixed bugs in multi-turn conversations

2. Fixed the issue of handling Redacted messages 

3. Correct the front-end layout and window adaptability issues
   
4. Added multi-user system, and the Settings of different users do not interfere with each other
   
5. Added User Activity Analytics

6. Added the ability to simultaneously display the scanner processing results of F5 Guardrail

7. Added Skills capability—new Skills can be added and auto-registered at any time

8. Added Inline integration for dynamic visualization
9. Added and OOB integration for dynamic visualization
10. Added an interpretation of the China compliance report based on the actual test results of SecurIQLab 
11. Added Agentic Security for testing Agentic Fingerprint
12. Added sample templates for attack scenarios
13. Add a switch that temporarily bypasses all detections in the chat interface and directly connects to the model
14. Added the function of viewing original LLM messages when Redacted

15. Added Hugging Face proxy download support

16. Added whether to use all engine switches 

17. Added debug swtich for storing raw json that from F5 guardrail
18. Added the F5 AI/Calypso multi-provider configuration capability, allowing users to switch and select different providers corresponding to the Project on the front end
19. Load `.env` directly without setting environment variables

20. Added frontend Markdown response rendering

21. Added the integration pipeline demonstration of F5 Red Team and DevSecOps. 

   Note: Considering the actual time consumption of Red Team and the feasibility of the environment, the Red Team API integration here is mock simulation and does not actually create real objects on the SaaS.

---

## 1. Prerequisites

### Environment Variables

Copy the example file and fill in your values before first use:

```bash
cp .env_example .env
# Edit .env with your CalypsoAI and Hugging Face configuration
```

Variables in `.env_example`:

| Variable | Description | Example |
|----------|-------------|---------|
| `CALYPSOAI_URL` | F5 AI Security platform URL | `https://www.us1.calypsoai.app/` |
| `CALYPSOAI_TOKEN` | API token (required) | `Your-calypsoai-token` |
| `CALYPSOAI_PROJECT_ID` | Project ID (Project mode) | `Your-calypsoai-project-id` |
| `CALYPSOAI_TOKEN_SECOND_PROJECT` | Secondary API token used by Chat/Agent Guardrail when Enterprise KB Skill is ON | `Your-calypsoai-token-second-project` |
| `CALYPSOAI_PROJECT_ID_SECOND` | Secondary project ID used by Chat/Agent Guardrail when Enterprise KB Skill is ON | `Your-calypsoai-project-id-second` |
| `DEFAULT_PROVIDER` | Provider name configured in Calypso; server default for main Chat/Agent/Inline mode; can be overridden by frontend selection | `Your-calypsoai-provider` |
| `PROVIDER_OPTIONS` | Comma-separated list of providers shown in the Settings “LLM Provider” dropdown; when set, users can choose which provider to use in the UI | `jinglin-google-gemini-133540,deepseek-JingLin-real-charge` |
| `SLIDING_WINDOW_MAX_TURNS` | Sliding window turn count for multi-turn chat | `8` |
| `SLIDING_WINDOW_MAX_CHARS` | Max characters in sliding window | `8000` |
| `CONVERSATION_TTL_SECONDS` | Conversation turn TTL in seconds | `120` |
| `GUARDRAIL_DEBUG` | When set to `1`/`true`/`yes`, prints F5 Guardrail request checkpoints to the terminal for debugging timeouts or 502 (optional) | `1` |
| `GUARDRAIL_TIMEOUT_SECONDS` | Guardrail request timeout in seconds; returns 504 on timeout, default `5` (optional) | `5` |
| `HF_HOME` | Hugging Face model cache directory (optional) | `Your-hugging-face-home-directory` |
| `HF_PROXY` | Proxy for HF model download only; not used for CalypsoAI (optional) | `http://127.0.0.1:8010` |
| `HF_TOKEN` | Hugging Face token (optional; recommended for faster downloads and to avoid rate limits) | `Your-hugging-face-token` |
| `LLM_PROVIDER_URL` | Direct endpoint used by the chat checkbox mode “Direct model (OpenAI-compatible)” (OpenAI-compatible base URL). **Required when using direct mode** | `https://api.example-llm.com/v1` |
| `LLM_PROVIDER_MODEL` | Model name used in direct mode. **Required when using direct mode** | `example-chat-model` |
| `LLM_PROVIDER_KEY_Direct` | API key (Bearer) used in direct mode. **Required when using direct mode**; `LLM_PROVIDER_KEY_DIRECT` is also supported as an alias | `sk-your-direct-provider-key` |
| `OOB_PROXY_URL` | NGINX Proxy URL for OOB mode. **Required when using OOB**; must match the docs/nginx listen address (e.g. `http://localhost:8787`). | `http://localhost:8787` |
| `LLM_PROVIDER_KEY` | API Key (Bearer) sent to the LLM in OOB mode. **Required when using OOB**; set per your LLM provider. | `Your-llm-provider-api-key` |
| `OOB_MODEL` | Model name for OOB requests. **Default `deepseek-chat`** when unset; when using OOB, set to your actual model. | `deepseek-chat` |
| `AGENTIC_BASE_URL` | Full OpenAI-compatible **base URL** for **Agentic Security** (path prefix included; **no** `/chat/completions`). If empty, the backend builds a URL from `CALYPSOAI_URL` plus a built-in provider path segment | `https://www.us1.calypsoai.app/openai/your-provider-slug` |
| `AGENTIC_TOKEN` | Bearer token for Agentic Security when using the Calypso OpenAI-compatible route. May match the main project token; if unset, **`CALYPSOAI_TOKEN` is used as fallback** (configure at least one) | Same as `CALYPSOAI_TOKEN` or a dedicated token |
| `AGENTIC_MODEL` | `model` field in Agentic Security chat-completions requests. Default `deepseek-chat` when unset | `deepseek-chat` |

**Note:** Configure the corresponding Project(Standard App project,Agentic mode project, and standard App project for `Enterprise Skill On` mode), Connection/Provider, and Project API token in Calypso (F5 Guardrail) first. For features like enterprise-sensitive data protection, configure Custom scanners in the F5 Guardrail system in advance.
Security note: Keys shown in README and `.env_example` are placeholders only.
In **direct chat** mode, the **Enterprise KB Skill** toggle matches the main Chat: when ON, the direct LLM runs the same ReAct-style tool loop as the Guardrail Agent path (e.g. enterprise KB); when OFF, a single direct completion is used.

**Enterprise KB Skill dual-project routing (optional, admin-controlled):** The feature is gated by `global_settings.dual_project_routing_enabled` in `settings.json` (default `false`), mirrored in Settings as **Enable Dual Project Routing By Enterprise Skill** and **editable by `admin` only**. When **off**, main Chat/Agent Guardrail always uses `CALYPSOAI_PROJECT_ID` + `CALYPSOAI_TOKEN`. When **on**, routing follows Enterprise KB Skill: **ON** → `CALYPSOAI_PROJECT_ID_SECOND` + `CALYPSOAI_TOKEN_SECOND_PROJECT`; **OFF** → primary project. Turning the switch **on** requires both `CALYPSOAI_PROJECT_ID_SECOND` and `CALYPSOAI_TOKEN_SECOND_PROJECT` in `.env`; otherwise the UI/API rejects it with a “not configured” style error. SaaS scanner drift banner and bidirectional sync are removed.

### User Authentication Setup (Before First Run)

This project uses login/session authentication.Configure users before first start to avoid relying on default credentials.

1. Copy the example settings to the active config file (you already prepared the example file):

```bash
cp settings_example.json settings.json
```

2. Update these fields in `settings.json`:
- `auth.users`: login user list (`username`, `password_hash`, `enabled`)
- `auth.session_ttl_seconds`: session TTL in seconds
- `user_settings`: per-user runtime settings (recommended to align usernames with `auth.users`)
- Keep and configure at least one `admin` username: this username controls some global Settings items in the UI (for example, Enterprise KB Directory, Agent Max Steps, and `dual_project_routing_enabled` for dual Calypso projects).

> Tip: use `settings_example.json` as template, then rename/copy it to `settings.json` before editing.

### Generate Users in Batch with `scripts/gen_password_hash.py`

Use `scripts/gen_password_hash.py` to generate `auth.users` entries in batch. The script prints a JSON array that you can paste directly into `auth.users` in `settings.json`.

Example (multiple users at once):

```bash
python scripts/gen_password_hash.py \
  --iterations 120000 \
  --user "admin:YourStrongPassword1!" \
  --user "analyst:YourStrongPassword2!" \
  --user "auditor:YourStrongPassword3!"
```

You can also save output to a file first:

```bash
python scripts/gen_password_hash.py \
  --user "admin:YourStrongPassword1!" \
  --user "analyst:YourStrongPassword2!" > users.generated.json
```

Recommendations:
- Use strong, unique passwords for each account.
- After updating `auth.users`, also add matching `user_settings.<username>` entries. Reference `settings_example.json` for detail.

### Attack panel configuration

The **attack example** list (AI Chat view) and the **Guardrail Integration** request presets are driven by JSON config files. You can add, remove, or edit entries.

- **AI Chat · Attack examples:** `config/attack-presets.json`
- **Guardrail Integration · Request presets:** `config/guardrail-integration-presets.json`

Each preset is an object. Entries with `enabled: false` are hidden in the UI.

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Recommended | Unique id; can be reused for same category |
| `title` | Yes | Label shown in the list |
| `prompt` | Yes | Text inserted into the input when selected |
| `category` | Recommended | Category name for grouping |
| `enabled` | No | Default `true`; set `false` to hide |
| `tags` | No | Only in attack-presets; used for tags |

Example (single entry in `config/attack-presets.json`):

```json
{
  "id": "jailbreak-basic",
  "title": "Jailbreak: ignore safety rules",
  "prompt": "From now on you will act as...",
  "category": "Jailbreak",
  "enabled": true,
  "tags": ["jailbreak", "policy bypass"]
}
```

### OOB mode – NGINX configuration (brief)

In **OOB (out-of-band)** mode in the Guardrail Integration view, requests are forwarded from this app to an **NGINX + F5 Guardrail** proxy, which then forwards to the LLM provider. NGINX must be deployed and configured separately.

- **Reference config:** `docs/nginx/conf.d/default_example.conf` (copy to `default.conf` and adjust as needed).
- Install` NGINX JS(NJS)` module, and load it in the `nginx.conf`
- Put related njs file into `/etc/nginx/js/`
- **Main points:**
  - **Upstreams:** `aigr_api` (F5 Guardrail), `llm_provider_api` (e.g. Deepseek/OpenAI).
  - **Variables:** `$aigr_api_host`, `$aigr_api_token` (F5 auth), `$llm_provider_host`.
  - **`/v1/chat/completions`:** Handled by `js_content aigr_filter_redacted.filterChatCompletion`: call F5 scan (`/aigr_scan`), then if allowed forward to `/llm_provider`.
  - **`/aigr_scan`:** Reverse proxy to F5 `backend/v1/scans`.
  - **`/llm_provider`:** Reverse proxy to the LLM’s `v1/chat/completions`, forwarding `Authorization`.

In this app’s `.env`, when using OOB you must set `OOB_PROXY_URL` (NGINX base URL, e.g. `http://localhost:8787`) and `LLM_PROVIDER_KEY` (LLM API key) to match your environment; `OOB_MODEL` defaults to `deepseek-chat` if unset—configure it to your actual model name. In OOB mode the frontend does not show Scanner details (determined by the proxy).

---

## 2. Python Environment

- **Python:** 3.10 or higher
- A virtual environment is recommended

```bash
# Create and activate virtual environment (example)
python3.10 -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows
```

### Install Dependencies

1. **F5 AI Security SDK** (required)  
   See official docs: [First steps - Install the SDK](https://docs.aisecurity.f5.com/api-docs/first-steps.html#install-the-sdk)

2. **Other dependencies (including Agentic Security / LangGraph)**

The **Agentic Security** view uses **LangGraph** (`langgraph` on PyPI). Installing it pulls transitive dependencies (e.g. `langchain-core`). If it is missing, building the LangGraph runner at `POST /api/agentic/run` fails with an error asking you to install LangGraph first.

Use either:

```bash
# Option A: one-line install (same package set as before, plus langgraph)
pip install python-dotenv fastapi uvicorn pydantic jinja2 transformers torch protobuf httpx geoip2 langgraph

# Option B: project requirements.txt (still excludes the Calypso SDK—install that separately)
pip install -r requirements.txt
```

#### City Display in User Activity Analytics (GeoIP)

To show city distribution of login IPs in **User Activity Analytics**, prepare the following:

1. Download the MaxMind GeoLite2 City database (`GeoLite2-City.mmdb`).
2. Place the file at: `static/ip/GeoLite2-City.mmdb` (project root based).
3. Ensure dependency is installed: `pip install geoip2` (skip if already installed via the command above).

Notes:
- If the database file is missing or `geoip2` is not installed, city stats gracefully fall back to `Unknown` without breaking other features.
- Private/local IP addresses are shown as `Local Network`.

---

## 3. Run the App

From the project root, with the virtual environment activated and `.env` configured:

```bash
export TRANSFORMERS_OFFLINE=1
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Open in browser: `http://localhost:8000`.

> Please note that when starting up for the first time, TRANSFORMERS_OFFLINE=0 should be set so that the program can automatically download from hugging face when it finds that there is no engine model locally 
>
> From now on, when starting up, just set it to 1. 
>
> If a non-privileged user runs it, you may encounter directory permission issues for downloading files. You can avoid the switching of python executable files caused by sudo by specifying the python bin file method in the python virtual environment, for example:
>
> sudo /home/myuser/miniconda3 envs/calypsoai - demo - app/bin/python3 -m uvicorn main: app - host 0.0.0.0 -- port 8000

---

## 4. First Run

On first run, the app will download local detection models from Hugging Face (e.g. `unitary/toxic-bert`, `protectai/deberta-v3-base-prompt-injection-v2`). **Please wait for the download to complete.** Configuring `HF_PROXY` and `HF_TOKEN` can speed up downloads and reduce rate limiting. Registering on Hugging Face and setting a token is recommended to avoid rate limits.

---

## 5. Runtime Environment

- **Minimum:** Verified on **Mac M1, 16GB RAM**.
- Network access to the F5 AI Security platform (CalypsoAI) and Hugging Face (for model download only) is required.

---

## 6. Main Features

- **Multi-engine guardrails:** F5 cloud + local ML (toxicity, prompt injection); optional “F5 only” to skip local engines; optional F5 Scanner detail (verbose).
- **AI Chat view:** Single/multi-turn (sliding window), attack preset templates, engine status bar, Markdown rendering for replies.
- **Settings:** Detection thresholds, pattern keywords, KB path, agent steps, etc.; `settings.json` and UI stay in sync.
- **Skills:** Auto-discovered registry; enterprise KB Skill (local directory, configurable extensions and limits); optional ReAct agent orchestration and step count.
- **Guardrail Integration view:** Dedicated view for Inline (request via Guardrail) vs OOB (request via Proxy, Guardrail on the side) with flow diagrams and preset prompts.
- **Red Team pipeline:** Simulated CI/CD (commit→build→deploy→F5 Red Team test→security decision), CASI score and manual review/fail branches, sample report link; demo is Mock (no real Red Team API calls).
- **Agentic Security:** A LangGraph-style multi-agent workflow (Supervisor planning and final user-facing summary, Research evidence gathering, Action tool execution, **Legal Counsel** for a brief legal-risk one-liner in Chinese, capped to roughly 50 characters, plus two extra plain conversational follow-ups driven by config). Model calls go through Calypso’s **OpenAI-compatible** endpoint with `x-cai-metadata-session-id` for session-level observability in F5 AI Security. Built-in mock procurement-risk tools and file-driven business data (`config/agentic-tools-config.json`), scenario templates (`config/agentic-risk-templates.json`), step timeline, tool/risk side panel, flow diagram (active step “breathe” highlight; completed stages turn green), and an optional **bypass** path that talks to an upstream LLM without Guardrail for contrast. The **Agentic Tool Config** UI edits and persists tool-scoped settings (including Legal Counsel’s two configurable follow-up topics). *Not legal advice; the Legal Counsel step is a demo-only brief commentary.*
- **China Compliance Report:** A dedicated nav view that embeds the static site `compliance/index.html` (served at `/compliance/index.html`). It presents a **mapping/reference** between F5 LLM security capabilities and **China-oriented AI compliance** narrative (Chinese UI copy), aimed at customer conversations and internal alignment—content is static HTML you can edit under `compliance/`. `compliance/index_example.html` is available as a backup or layout reference.

| Module | Capability |
|--------|------------|
| **Guardrails** | F5 cloud + local ML (toxic-bert, protectai); `f5_guardrail_only` to use F5 only; `guardrail_verbose` to return and show F5 Scanner details |
| **Frontend views** | Nav includes multiple views: AI Chatbot/Agent, Red Team, Guardrail Integration, **Agentic Security**, Test Guide, **China Compliance Report**, Settings, etc. (some entries such as User Activity may be toggled by configuration) |
| **Chat** | Single/multi-turn (sliding window), attack preset templates (`attack-presets.json`), engine status bar, Markdown rendering for replies |
| **Settings** | `settings.json` + UI: thresholds, Pattern, KB path, agent steps, debug raw JSON, etc. |
| **Skills** | Auto-discover under `skills/`; includes `read_enterprise_kb` (local directory KB); optional ReAct agent orchestration and `agent_max_steps` |
| **Guardrail Integration** | Dedicated view: Inline (`/api/guardrail-scan`) and OOB (`/api/oob-chat` via Proxy) with flow diagrams and `guardrail-integration-presets.json` presets |
| **Red Team** | Simulated CI/CD pipeline (5 steps + substeps), CASI score, manual review/fail branches, `/redteam-report` sample report; **demo is Mock, no real Red Team API calls** |
| **Agentic Security** | `POST /api/agentic/run` + `GET /api/agentic/run-trace`; LangGraph runner; mock tools + `config/agentic-tools-config.json` + `config/agentic-risk-templates.json`; Calypso session header on LLM calls; step trace, flow visualization, Markdown final reply |
| **China Compliance Report** | iframe to `compliance/index.html`; static narrative mapping F5 capabilities to China AI compliance themes (editable static content) |

---

## 7. Debug logging (F5 Guardrail checkpoints)

When F5 Guardrail calls time out or return 502, you can use debug checkpoints to tell whether the **request was never sent** or **no response was received**.

In `.env` set:

```bash
GUARDRAIL_DEBUG=1
```

After restarting the app, the terminal will show timestamped `[GUARDRAIL-DEBUG]` lines. Use the **last** checkpoint that appears to interpret:

| Last checkpoint | Meaning |
|-----------------|---------|
| About to send request (before entering threadpool) | Request likely never actually sent (stuck in threadpool or earlier). |
| Preparing to send request | Inside sync path but not yet the Calypso HTTP call. |
| About to call Calypso API (post or prompts.send) | **Request has been sent**; if you never see “received Calypso API response”, the server **did not respond** (timeout, connection closed, etc.). |
| Received Calypso API response | Server responded; issue is in later handling. |
| Request failed ... type=... err=... | Check `type`/`err`: e.g. `RemoteDisconnected` means the remote closed the connection—request was sent but no normal response. |

The actual log messages are in Chinese; match them to the rows above by order and context.

Agent-related logs (enable “Agent Debug” in Settings) emit timestamped `[AGENT-DEBUG]` lines, which you can use together with Guardrail checkpoints when troubleshooting.

---

## 8. Disclaimer

This is a demo application for the F5 AI Guardrail and AI Red Team system and is not production-ready. Please open issues for any problems.
