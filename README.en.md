# F5 AI Guardrail and Red Team Demo App

A multi-engine AI guardrail demo Agent application based on F5 AI Guardrail (CalypsoAI) and local ML engines. It provides a web chat interface with configurable prompt/response detection policies and integrates Skills to simulate enterprise system integration.

![image-20260315091559488](README.assets/image-20260315091559488.png)

![screencapture-127-0-0-1-8000-2026-03-15-09_21_04](README.assets/screencapture-127-0-0-1-8000-2026-03-15-09_21_04.png)

![F5-Red-Team-DevSecOps-failure](README.assets/F5-Red-Team-DevSecOps-failure.png)

**Credits:** This app is an improvement on James Lee's demo, including but not limited to:

1. Fixed bugs in multi-turn conversations

2. Fixed the issue of handling Redacted messages 

3. Correct the front-end layout and window adaptability issues

4. Added the ability to simultaneously display the scanner processing results of F5 Guardrail

5. Added Skills capability—new Skills can be added and auto-registered at any time

6. Added Inline integration for dynamic visualization
7. Added and OOB integration for dynamic visualization
8. Added sample templates for attack scenarios

9. Added Hugging Face proxy download support

10. Added whether to use all engine switches 

11. Added debug swtich for storing raw json that from F5 guardrail
12. Load `.env` directly without setting environment variables

13. Added frontend Markdown response rendering

14. Added the integration pipeline demonstration of F5 Red Team and DevSecOps. 

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
| `DEFAULT_PROVIDER` | Provider name configured in Calypso | `Your-calypsoai-provider` |
| `SLIDING_WINDOW_MAX_TURNS` | Sliding window turn count for multi-turn chat | `8` |
| `SLIDING_WINDOW_MAX_CHARS` | Max characters in sliding window | `8000` |
| `CONVERSATION_TTL_SECONDS` | Conversation turn TTL in seconds | `120` |
| `HF_HOME` | Hugging Face model cache directory (optional) | `Your-hugging-face-home-directory` |
| `HF_PROXY` | Proxy for HF model download only (optional) | `http://127.0.0.1:8010` |
| `HF_TOKEN` | Hugging Face token (optional; recommended for faster downloads) | `Your-hugging-face-token` |
| `OOB_PROXY_URL` | NGINX Proxy URL for OOB mode. **Required when using OOB**; set to your actual deployment (e.g. `http://localhost:8787`). | `http://localhost:8787` |
| `LLM_PROVIDER_KEY` | API Key (Bearer) sent to the LLM in OOB mode. **Required when using OOB**; set per your LLM provider. | `Your-llm-provider-api-key` |
| `OOB_MODEL` | Model name for OOB requests. **Default `deepseek-chat`** when unset; when using OOB, set to your actual model. | `deepseek-chat` |

**Note:** Configure the corresponding Project, Connection/Provider, and Project API token in Calypso (F5 Guardrail) first. For features like enterprise-sensitive data protection, configure Custom scanners in the F5 Guardrail system in advance.

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

2. **Other dependencies**

```bash
pip install python-dotenv fastapi uvicorn pydantic jinja2 transformers torch protobuf
```

---

## 3. Run the App

From the project root, with the virtual environment activated and `.env` configured:

```bash
export TRANSFORMERS_OFFLINE=1
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Open in browser: `http://localhost:8000`.

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

| Module | Capability |
|--------|------------|
| **Guardrails** | F5 cloud + local ML (toxic-bert, protectai); `f5_guardrail_only` to use F5 only; `guardrail_verbose` to return and show F5 Scanner details |
| **Frontend views** | Four entries: AI Chatbot/Agent, Red Team, Guardrail Integration, Settings |
| **Chat** | Single/multi-turn (sliding window), attack preset templates (`attack-presets.json`), engine status bar, Markdown rendering for replies |
| **Settings** | `settings.json` + UI: thresholds, Pattern, KB path, agent steps, debug raw JSON, etc. |
| **Skills** | Auto-discover under `skills/`; includes `read_enterprise_kb` (local directory KB); optional ReAct agent orchestration and `agent_max_steps` |
| **Guardrail Integration** | Dedicated view: Inline (`/api/guardrail-scan`) and OOB (`/api/oob-chat` via Proxy) with flow diagrams and `guardrail-integration-presets.json` presets |
| **Red Team** | Simulated CI/CD pipeline (5 steps + substeps), CASI score, manual review/fail branches, `/redteam-report` sample report; **demo is Mock, no real Red Team API calls** |

---

## 7. Disclaimer

This is a demo application for the F5 AI Guardrail and AI Red Team system and is not production-ready. Please open issues for any problems.
