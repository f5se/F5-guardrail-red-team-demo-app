import os
import time
import json
import re
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Deque, Dict, List, Optional, Tuple
from urllib.request import Request as UrlRequest, urlopen
from urllib.error import HTTPError, URLError

from dotenv import load_dotenv

# 优先从脚本所在目录加载 .env，避免因启动目录不同而读不到 PROVIDER_OPTIONS 等
_script_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_script_dir, ".env"))
load_dotenv()  # 再允许当前工作目录 .env 覆盖

# 仅 Hugging Face 模型下载走代理；CalypsoAI 不走代理。
# 在 .env 中设置 HF_PROXY 或 PROXY，例如: HF_PROXY=http://127.0.0.1:7890
# -----------------------------
HF_PROXY = os.getenv("HF_PROXY") or os.getenv("PROXY")

from fastapi import FastAPI, Request, HTTPException, Body
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
import httpx

from calypsoai import CalypsoAI
import calypsoai.datatypes as cai_dt
from transformers import pipeline

from skills import get_all_tool_definitions, dispatch_tool
from skills.utils import to_bool, to_int, to_float, normalize_extensions, agent_debug_log

# Project-root anchored paths to avoid cwd mismatch.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# -----------------------------
# ENV
# -----------------------------
CALYPSOAI_URL = os.getenv("CALYPSOAI_URL")
CALYPSOAI_TOKEN = os.getenv("CALYPSOAI_TOKEN")
CALYPSOAI_PROJECT_ID = os.getenv("CALYPSOAI_PROJECT_ID")  # your requirement
DEFAULT_PROVIDER = os.getenv("DEFAULT_PROVIDER")
# Hugging Face：用于模型下载，可提升速率并避免匿名 API 限制。在 .env 中设置 HF_TOKEN=hf_xxx
HF_TOKEN = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")

SLIDING_WINDOW_MAX_TURNS = int(os.getenv("SLIDING_WINDOW_MAX_TURNS", "8"))
SLIDING_WINDOW_MAX_CHARS = int(os.getenv("SLIDING_WINDOW_MAX_CHARS", "2000"))

CONVERSATION_TTL_SECONDS = int(os.getenv("CONVERSATION_TTL_SECONDS", "120"))  # 2 minutes

# OOB 旁路模式：Proxy(NGINX) 地址与 LLM Provider API Key
OOB_PROXY_URL = (os.getenv("OOB_PROXY_URL") or "").rstrip("/")
LLM_PROVIDER_KEY = os.getenv("LLM_PROVIDER_KEY") or ""

# Guardrail 调用打点：设为 1/true/yes 时打印，用于判断「请求未发出」vs「未收到响应」
GUARDRAIL_DEBUG = os.getenv("GUARDRAIL_DEBUG", "").lower() in ("1", "true", "yes")


def _guardrail_debug(msg: str):
    if GUARDRAIL_DEBUG:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        print(f"[GUARDRAIL-DEBUG] {ts} {msg}")


if not CALYPSOAI_TOKEN:
    raise RuntimeError("CALYPSOAI_TOKEN must be set")

cai = CalypsoAI(url=CALYPSOAI_URL, token=CALYPSOAI_TOKEN)
print("Loading local ML engines...")

# 仅在此阶段设置代理，供 Hugging Face 模型下载使用；下载完成后清除，CalypsoAI 不走代理
_proxy_keys = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")
if HF_PROXY:
    for k in _proxy_keys:
        os.environ[k] = HF_PROXY

tox_model = pipeline(
    "text-classification",
    model="unitary/toxic-bert",
    token=HF_TOKEN,
)

pi_model = pipeline(
    "text-classification",
    model="protectai/deberta-v3-base-prompt-injection-v2",
    token=HF_TOKEN,
)

if HF_PROXY:
    for k in _proxy_keys:
        os.environ.pop(k, None)

print("ML engines loaded.")

app = FastAPI()

# 静态资源挂载（使用项目根路径，避免工作目录变化导致 404）
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(BASE_DIR, "static")),
    name="static",
)

# Red Team 自定义报告目录挂载，供前端直接访问 HTML 报告
app.mount(
    "/redteam-report",
    StaticFiles(directory=os.path.join(BASE_DIR, "redteam-report"), html=True),
    name="redteam-report",
)

templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


# -----------------------------
# Attack presets config
# -----------------------------
ATTACK_PRESETS_FILE = os.path.join(BASE_DIR, "config", "attack-presets.json")
GUARDRAIL_INTEGRATION_PRESETS_FILE = os.path.join(BASE_DIR, "config", "guardrail-integration-presets.json")


def load_attack_presets() -> List[dict]:
    """
    Load attack presets from config/attack-presets.json.
    Fail-safe: on any error, return empty list so that UI can handle gracefully.
    """
    try:
        if not os.path.exists(ATTACK_PRESETS_FILE):
            return []
        with open(ATTACK_PRESETS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        # Filter out disabled presets and ensure required keys exist
        presets: List[dict] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            if item.get("enabled", True) is False:
                continue
            title = str(item.get("title") or "").strip()
            prompt = str(item.get("prompt") or "").strip()
            if not title or not prompt:
                continue
            presets.append(
                {
                    "id": str(item.get("id") or title),
                    "title": title,
                    "prompt": prompt,
                    "category": str(item.get("category") or "未分类"),
                }
            )
        return presets
    except Exception:
        # Any parsing error just results in no presets; details can be inspected via server logs if needed.
        return []


def load_guardrail_integration_presets() -> List[dict]:
    """
    Load attack presets for Guardrail Integration view from config/guardrail-integration-presets.json.
    Same structure as attack-presets.json; fail-safe returns empty list on error.
    """
    try:
        if not os.path.exists(GUARDRAIL_INTEGRATION_PRESETS_FILE):
            return []
        with open(GUARDRAIL_INTEGRATION_PRESETS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        presets: List[dict] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            if item.get("enabled", True) is False:
                continue
            title = str(item.get("title") or "").strip()
            prompt = str(item.get("prompt") or "").strip()
            if not title or not prompt:
                continue
            presets.append(
                {
                    "id": str(item.get("id") or title),
                    "title": title,
                    "prompt": prompt,
                    "category": str(item.get("category") or "未分类"),
                }
            )
        return presets
    except Exception:
        return []


# -----------------------------
# In-memory conversation store
# conversation_id -> deque of turns (strings)
# -----------------------------
ConversationStore = Dict[str, Deque[dict]]
conversations: ConversationStore = defaultdict(lambda: deque(maxlen=SLIDING_WINDOW_MAX_TURNS))

# -----------------------------
# Models
# -----------------------------
class ChatIn(BaseModel):
    message: str
    conversation_id: str
    multi_turn: bool = False
    provider: Optional[str] = None  # 可选，覆盖当前默认 Provider（主 Chat/Agent 用）


# -----------------------------
# UI Routes
# -----------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    attack_presets = load_attack_presets()
    guardrail_integration_presets = load_guardrail_integration_presets()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "attack_presets_json": json.dumps(attack_presets, ensure_ascii=False),
            "guardrail_integration_presets_json": json.dumps(guardrail_integration_presets, ensure_ascii=False),
        },
    )


@app.get("/health")
async def health():
    return {"status": "ok", "ts": int(time.time())}


# -----------------------------
# Helpers
# -----------------------------
def build_send_kwargs(*, verbose: bool = False, provider_override: Optional[str] = None) -> dict:
    if CALYPSOAI_PROJECT_ID:
        # project: SDK/API 要求的项目标识。
        # provider: 优先用 provider_override（前端选择或请求体），否则用 env DEFAULT_PROVIDER，供 F5/Calypso 路由与展示。
        # verbose: True 时通过底层 client 传 PostPromptsBody.verbose，返回更详细的 scanner 信息（SDK 的 prompts.send() 未暴露该参数，故需走 client）。
        kwargs = {"project": CALYPSOAI_PROJECT_ID}
        effective_provider = (provider_override or "").strip() or (DEFAULT_PROVIDER or "").strip()
        if effective_provider:
            kwargs["provider"] = effective_provider
        if verbose:
            kwargs["verbose"] = True
        return kwargs

    # Fallback if no Project ID is set (optional, depending on your logic)
    raise HTTPException(status_code=500, detail="CALYPSOAI_PROJECT_ID is not set")

def cleanup_conversation(conversation_id: str):
    now = time.time()
    q = conversations[conversation_id]

    # Remove old turns from the left (oldest first)
    while q and (now - q[0]["ts"] > CONVERSATION_TTL_SECONDS):
        q.popleft()

    # Optional: if it becomes empty, you can remove the key entirely
    if not q and conversation_id in conversations:
        try:
            del conversations[conversation_id]
        except KeyError:
            pass

def build_sliding_window_prompt(conversation_id: str, new_user_message: str) -> str:
    # Ensure ID exists
    if conversation_id not in conversations:
        conversations[conversation_id] = deque(maxlen=SLIDING_WINDOW_MAX_TURNS)

    cleanup_conversation(conversation_id)

    # Get only the raw text from previous user turns
    history_texts = [turn['text'] for turn in conversations[conversation_id]]

    # Append the new message
    history_texts.append(new_user_message)

    # Join with a space (or ". " if you prefer) to create one raw block of text
    # Example: "Hello" + "My name is John" -> "Hello My name is John"
    prompt = " ".join(history_texts)

    if len(prompt) > SLIDING_WINDOW_MAX_CHARS:
        prompt = prompt[-SLIDING_WINDOW_MAX_CHARS:]

    return prompt

def classify_rejection(reply: str) -> tuple[str, Optional[str]]:
    """
    Keep your existing UX behavior: detect rejection banners.
    """
    if not isinstance(reply, str):
        return "error", None

    t = reply.strip()
    if t.startswith("Prompt Rejected"):
        return "rejected", "prompt"
    if t.startswith("Response Rejected"):
        return "rejected", "response"
    return "ok", None

SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")
print(f"[CONFIG] SETTINGS_FILE={SETTINGS_FILE}")

DEFAULT_SETTINGS = {
    "patterns": "ignore:3\nsystem:3\nprompt:2",
    "heuristic_threshold": 10,
    "toxic_threshold": 0.75,
    "pi_threshold": 0.7,
    "agent_skill_enabled": False,
    "f5_guardrail_only": False,
    "debug_guardrail_raw_enabled": False,
    "guardrail_verbose": False,
    "kb_dir": "./enterprise_kb",
    "agent_max_steps": 4,
    "agent_debug_enabled": False,
    "kb_top_k": 3,
    "kb_allowed_extensions": ".txt,.md,.json,.csv",
    "kb_max_file_chars": 8000,
    "kb_max_result_chars": 5000,
    "default_provider": "",  # 前端可选；空则用 env DEFAULT_PROVIDER
}

def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return DEFAULT_SETTINGS.copy()
    with open(SETTINGS_FILE) as f:
        loaded = json.load(f)
    merged = DEFAULT_SETTINGS.copy()
    if isinstance(loaded, dict):
        merged.update(loaded)
    return merged

def parse_patterns(raw: str) -> dict:
    result = {}
    for line in raw.split("\n"):
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        try:
            result[k.strip().lower()] = int(v.strip())
        except:
            pass
    return result

def get_runtime_settings(raw: dict) -> dict:
    patterns = raw.get("patterns", DEFAULT_SETTINGS["patterns"])
    if not isinstance(patterns, str):
        patterns = str(patterns)
    return {
        "patterns": patterns,
        "heuristic_threshold": to_int(raw.get("heuristic_threshold", 10), 10, 1, 100),
        "toxic_threshold": to_float(raw.get("toxic_threshold", 0.75), 0.75, 0.0, 1.0),
        "pi_threshold": to_float(raw.get("pi_threshold", 0.7), 0.7, 0.0, 1.0),
        "agent_skill_enabled": to_bool(raw.get("agent_skill_enabled", False)),
        "f5_guardrail_only": to_bool(raw.get("f5_guardrail_only", False)),
        "debug_guardrail_raw_enabled": to_bool(raw.get("debug_guardrail_raw_enabled", False)),
        "guardrail_verbose": to_bool(raw.get("guardrail_verbose", False)),
        "kb_dir": str(raw.get("kb_dir") or "./enterprise_kb"),
        "agent_max_steps": to_int(raw.get("agent_max_steps", 4), 4, 1, 8),
        "agent_debug_enabled": to_bool(raw.get("agent_debug_enabled", False)),
        "kb_top_k": to_int(raw.get("kb_top_k", 3), 3, 1, 8),
        "kb_allowed_extensions": normalize_extensions(raw.get("kb_allowed_extensions", ".txt,.md,.json,.csv")),
        "kb_max_file_chars": to_int(raw.get("kb_max_file_chars", 8000), 8000, 500, 50000),
        "kb_max_result_chars": to_int(raw.get("kb_max_result_chars", 5000), 5000, 500, 20000),
        "default_provider": str(raw.get("default_provider", "") or ""),
    }

def format_guardrail_reply(data: dict) -> str:
    guardrail_result = (data.get("result") or {})
    outcome = guardrail_result.get("outcome")
    if outcome == "cleared" or outcome == "redacted":
        return guardrail_result.get("response", "") or "(empty response)"
    calypso_type = str(data.get("type", "")).lower()
    label = "Response" if calypso_type == "response" else "Prompt"
    return (
        f"{label} Rejected\n\n"
        f"The requested {label} was rejected by F5 AI Guardrail because it violated "
        "the company's AI security policy."
    )

def _call_f5_guardrail_sync(prompt_to_send: str, send_kwargs: dict):
    """同步调用 F5 Guardrail。若 send_kwargs 含 verbose=True，走底层 client 以传 verbose；否则走 cai.prompts.send。主 Chat/Agent/Inline 的 provider 由 build_send_kwargs 传入。"""
    _guardrail_debug(f"sync: 准备发送请求 prompt_len={len(prompt_to_send or '')}")
    use_verbose = send_kwargs.pop("verbose", False)
    project = send_kwargs.get("project")
    provider = send_kwargs.get("provider")
    if use_verbose and project is not None:
        body_kw = dict(
            input=prompt_to_send,
            project=project,
            skipScanning=False,
            verbose=True,
        )
        if provider:
            body_kw["provider"] = provider
        try:
            body = cai_dt.PostPromptsBody(**body_kw)
        except TypeError:
            # SDK 的 PostPromptsBody 可能不支持 provider，仅用必选字段重试
            body_kw.pop("provider", None)
            body = cai_dt.PostPromptsBody(**body_kw)
        _guardrail_debug("sync: 已调用 Calypso API (client.prompts.post)")
        response = cai.client.prompts.post(body)
        _guardrail_debug("sync: 已收到 Calypso API 响应 (post)")
        # verbose 的 POST 响应已包含完整 JSON，根下含 scanners（友好名），直接从此响应提取
        out = response.model_dump() if hasattr(response, "model_dump") else {}
        if getattr(response, "scanners", None) is not None:
            out["scanners"] = response.scanners.model_dump() if hasattr(response.scanners, "model_dump") else response.scanners
        else:
            out.setdefault("scanners", {})
        return out
    _guardrail_debug("sync: 已调用 Calypso API (prompts.send)")
    out = cai.prompts.send(prompt_to_send, **send_kwargs)
    _guardrail_debug("sync: 已收到 Calypso API 响应 (send)")
    return out


async def call_f5_guardrail(prompt_to_send: str, send_kwargs: dict) -> Tuple[str, dict]:
    _guardrail_debug("call_f5_guardrail: 即将发起请求（进入线程池前）")
    try:
        # send_kwargs 会被 _call_f5_guardrail_sync  pop 掉 verbose，复制一份避免影响调用方
        kwargs = dict(send_kwargs)
        result = await run_in_threadpool(_call_f5_guardrail_sync, prompt_to_send, kwargs)
        _guardrail_debug("call_f5_guardrail: 已收到服务端完整响应")
        data = result if isinstance(result, dict) else result.model_dump()
    except Exception as e:
        _guardrail_debug(
            f"call_f5_guardrail: 请求失败（已发出则说明未收到响应或连接被关闭） "
            f"type={type(e).__name__} err={e!r}"
        )
        raise HTTPException(status_code=502, detail=f"Failed to call Guardrail: {e}")
    return format_guardrail_reply(data), data

def extract_json_object(text: str) -> Tuple[Optional[dict], Optional[str]]:
    raw = (text or "").strip()
    if not raw:
        return None, "empty model output"
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None, "no json object found"
    body = raw[start:end + 1]
    try:
        obj = json.loads(body)
    except Exception as e:
        return None, f"json parse failed: {e}"
    if not isinstance(obj, dict):
        return None, "json object must be dict"
    return obj, None

def build_agent_prompt(user_input: str, scratchpad: str, tool_defs: List[dict], step: int, max_steps: int) -> str:
    tools_json = json.dumps(tool_defs, ensure_ascii=False, indent=2)
    return (
        "You are an agent runtime planner.\n"
        "Your job is to decide either a tool call or final answer.\n"
        "Output must be STRICT JSON only, no markdown.\n\n"
        f"[STEP]\n{step}/{max_steps}\n\n"
        "[TOOLS]\n"
        f"{tools_json}\n\n"
        "[RULES]\n"
        "1) If the user asks for enterprise/private/internal company knowledge, call tool first.\n"
        "2) If enough observations exist, return final answer.\n"
        "3) JSON output must be exactly one object.\n"
        "4) Tool call format: {\"type\":\"tool_call\",\"name\":\"read_enterprise_kb\",\"arguments\":{\"query\":\"...\",\"top_k\":3}}\n"
        "5) Final format: {\"type\":\"final\",\"answer\":\"...\"}\n\n"
        "[USER_INPUT]\n"
        f"{user_input}\n\n"
        "[SCRATCHPAD]\n"
        f"{scratchpad or '(none)'}\n"
    )

async def run_agent_skill_loop(user_input: str, send_kwargs: dict, settings: dict) -> dict:
    max_steps = settings["agent_max_steps"]
    tool_defs = get_all_tool_definitions()
    scratchpad_entries: List[str] = []
    trace: List[dict] = []
    tool_calls: List[dict] = []
    last_guardrail_data: Optional[dict] = None
    agent_debug_log(
        settings,
        f"skill_loop start max_steps={max_steps} user_input_chars={len(user_input)}",
    )

    for step in range(1, max_steps + 1):
        prompt = build_agent_prompt(
            user_input=user_input,
            scratchpad="\n".join(scratchpad_entries),
            tool_defs=tool_defs,
            step=step,
            max_steps=max_steps,
        )
        reply, data = await call_f5_guardrail(prompt, send_kwargs)
        last_guardrail_data = data
        outcome = ((data.get("result") or {}).get("outcome") or "").lower()
        agent_debug_log(settings, f"skill_loop step={step} outcome={outcome or 'unknown'}")
        if outcome not in ("cleared", "redacted"):
            agent_debug_log(settings, f"skill_loop stop_on_guardrail_reject step={step}")
            return {
                "reply": reply,
                "trace": trace,
                "tool_calls": tool_calls,
                "skill_used": len(tool_calls) > 0,
                "guardrail": last_guardrail_data,
            }

        obj, parse_err = extract_json_object(reply)
        if parse_err:
            agent_debug_log(settings, f"skill_loop parse_error step={step} err={parse_err}")
            trace.append({"step": step, "event": "parse_error", "detail": parse_err})
            scratchpad_entries.append(
                f"Observation(parse_error): {parse_err}. raw_reply={reply[:400]}"
            )
            continue

        event_type = str(obj.get("type", "")).lower()
        if event_type == "final":
            answer = str(obj.get("answer", "")).strip() or "(empty response)"
            agent_debug_log(settings, f"skill_loop final step={step} answer_chars={len(answer)}")
            trace.append({"step": step, "event": "final"})
            return {
                "reply": answer,
                "trace": trace,
                "tool_calls": tool_calls,
                "skill_used": len(tool_calls) > 0,
                "guardrail": last_guardrail_data,
            }

        if event_type != "tool_call":
            agent_debug_log(settings, f"skill_loop invalid_event step={step} event_type={event_type or 'missing'}")
            trace.append({"step": step, "event": "invalid_event", "detail": event_type or "missing type"})
            scratchpad_entries.append(f"Observation(error): invalid event type={event_type or 'missing'}")
            continue

        tool_name = str(obj.get("name", "")).strip()
        arguments = obj.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {}

        trace.append({"step": step, "event": "tool_call", "name": tool_name})
        tool_calls.append({"step": step, "name": tool_name, "arguments": arguments})
        agent_debug_log(settings, f"skill_loop tool_call step={step} name={tool_name}")

        tool_result = dispatch_tool(tool_name, arguments, settings)

        compact_result = json.dumps(tool_result, ensure_ascii=False)
        agent_debug_log(
            settings,
            f"skill_loop tool_result step={step} ok={tool_result.get('ok', False)}",
        )
        scratchpad_entries.append(
            f"Action: {tool_name}({json.dumps(arguments, ensure_ascii=False)})\n"
            f"Observation: {compact_result[:1500]}"
        )

    fallback = "I could not finish the tool reasoning loop in time. Please retry with a more specific request."
    agent_debug_log(settings, "skill_loop fallback_max_steps_reached")
    return {
        "reply": fallback,
        "trace": trace,
        "tool_calls": tool_calls,
        "skill_used": len(tool_calls) > 0,
        "guardrail": last_guardrail_data,
    }

# -----------------------------
# API used by the UI
# -----------------------------
@app.post("/api/chat")
async def api_chat(payload: ChatIn):
    user_message = (payload.message or "").strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Message is required")

    conversation_id = (payload.conversation_id or "").strip()
    if not conversation_id:
        raise HTTPException(status_code=400, detail="conversation_id is required")

    raw_settings = load_settings()
    settings = get_runtime_settings(raw_settings)
    agent_debug_log(
        settings,
        f"api_chat start conversation_id={conversation_id} multi_turn={payload.multi_turn}",
    )
    effective_provider = (payload.provider or "").strip() or (raw_settings.get("default_provider") or "").strip() or DEFAULT_PROVIDER
    send_kwargs = build_send_kwargs(verbose=settings.get("guardrail_verbose", False), provider_override=effective_provider or None)

    # Single-turn vs multi-turn

    # Ensure no stale memory when multi-turn starts
    if payload.multi_turn and conversation_id not in conversations:
        conversations.pop(conversation_id, None)

    if payload.multi_turn:
        prompt_to_send = build_sliding_window_prompt(conversation_id, user_message)
    else:
        # Always clear before single-turn
        conversations.pop(conversation_id, None)
        prompt_to_send = user_message

    # F5 Guardrail path: skill orchestration applies only here
    agent_trace = []
    agent_tool_calls = []
    skill_used = False
    if settings["agent_skill_enabled"]:
        agent_debug_log(settings, "api_chat mode=agent_skill_enabled")
        loop_result = await run_agent_skill_loop(prompt_to_send, send_kwargs, settings)
        reply = loop_result["reply"]
        agent_trace = loop_result["trace"]
        agent_tool_calls = loop_result["tool_calls"]
        skill_used = loop_result["skill_used"]
        guardrail_raw = loop_result.get("guardrail")
    else:
        agent_debug_log(settings, "api_chat mode=plain_guardrail")
        reply, guardrail_raw = await call_f5_guardrail(prompt_to_send, send_kwargs)

    # Convert outcome to reply text
    if payload.multi_turn:
        cleanup_conversation(conversation_id)

        # Store ONLY the raw user message.
        # No "USER:" prefix, and no Assistant reply is stored.
        conversations[conversation_id].append({
            "ts": time.time(), 
            "text": user_message 
        })

    if not payload.multi_turn:
        conversations.pop(conversation_id, None)

    status, rejection_type = classify_rejection(reply)
    
    # ======================
    # LOCAL ENGINE DETECTION (skipped when f5_guardrail_only is True)
    # Single-turn and multi-turn both respect this setting.
    # ======================
    f5_only = settings.get("f5_guardrail_only", False)
    if f5_only:
        agent_debug_log(settings, "api_chat f5_guardrail_only=True, skipping local engines")
        engines = {
            "pattern": {"status": "IDLE", "score": "—"},
            "heuristic": {"status": "IDLE", "score": "—"},
            "toxic": {"status": "IDLE", "score": "—"},
            "protectai": {"status": "IDLE", "score": "—"},
            "f5": {"status": "BLOCK" if status == "rejected" else "PASS"}
        }
    else:
        heuristic_threshold = settings["heuristic_threshold"]
        toxic_threshold = settings["toxic_threshold"]
        pi_threshold = settings["pi_threshold"]
        
        pattern_map = parse_patterns(settings["patterns"])
        # Keep local engines aligned with Guardrail input:
        # multi-turn => full sliding-window context, single-turn => current user message.
        local_engine_input = prompt_to_send
        msg_lower = local_engine_input.lower()

        # Pattern Engine
        matched_keyword = next((k for k in pattern_map if k in msg_lower), None)

        # Heuristic Engine
        heuristic_score = sum(
            pattern_map[k] for k in pattern_map if k in msg_lower
        )
        
        # Toxic Engine
        try:
            # Run blocking model in a separate thread
            tox_results = await run_in_threadpool(tox_model, local_engine_input)
            tox_r = tox_results[0]
            tox_block = tox_r["score"] >= toxic_threshold
            tox_score = round(float(tox_r.get("score", 0)), 4)
            tox_label = tox_r.get("label", "unknown")
        except Exception as e:
            print(f"Toxic-BERT failed: {e}")
            tox_block = False
            tox_score = 0.0
            tox_label = "ERROR"

        # LLM Guard Engine (ProtectAI local model)
        try:
            pi_results = await run_in_threadpool(pi_model, local_engine_input)
            pi_r = pi_results[0]
            #pi_r = pi_model(user_message)[0]
        except Exception as e:
            print("ProtectAI failed:", e)
            pi_r = {"score": 0.0, "label": "SAFE"}

        pi_label = pi_r.get("label", "SAFE") # Extract ProtectAI label
        pi_score = float(pi_r.get("score", 0))

        # GOAL 1 FIX: Only block if the label indicates an attack.
        if pi_label == "SAFE":
            pi_block = False
        else:
            pi_block = pi_score >= pi_threshold

        engines = {
            "pattern": {
                "status": "BLOCK" if matched_keyword else "PASS",
                "score": matched_keyword or "clean"
            },
            "heuristic": {
                "status": "BLOCK" if heuristic_score >= heuristic_threshold else "PASS",
                "score": heuristic_score
            },
            "toxic": {
                "status": "BLOCK" if tox_block else "PASS",
                #"score": round(float(tox_r.get("score", 0)), 4),
                "score": tox_score,
                "label": tox_label # GOAL 2 FIX: Send label to frontend
            },
            "protectai": {
                "status": "BLOCK" if pi_block else "PASS",
                "score": round(float(pi_score), 4),
                "label": pi_label # GOAL 2 FIX: Send label to frontend
            },
            "f5": {
                "status": "BLOCK" if status == "rejected" else "PASS"
            }
        }

    # Optional debug: save raw F5 Guardrail response to .cursor for inspection
    if settings.get("debug_guardrail_raw_enabled") and isinstance(guardrail_raw, dict):
        try:
            _debug_path = os.path.join(BASE_DIR, ".cursor", "guardrail_response_debug.json")
            os.makedirs(os.path.dirname(_debug_path), exist_ok=True)
            with open(_debug_path, "w", encoding="utf-8") as _df:
                json.dump(guardrail_raw, _df, default=str, indent=2, ensure_ascii=False)
        except Exception:
            pass

    guardrail_payload = _build_guardrail_payload(guardrail_raw)

    response_body = {
        "reply": reply,
        "status": status,
        "rejection_type": rejection_type,
        "engines": engines,
        "mode": "project" if CALYPSOAI_PROJECT_ID else "provider",
        "multi_turn": payload.multi_turn,
        "skill_used": skill_used,
        "agent_trace": agent_trace,
        "agent_tool_calls": agent_tool_calls,
    }
    if guardrail_payload is not None:
        response_body["guardrail"] = guardrail_payload

    return JSONResponse(response_body)


def _build_guardrail_payload(guardrail_raw: Optional[dict]) -> Optional[dict]:
    """Build frontend-safe guardrail payload from raw F5 response. Used by api_chat and api_guardrail_scan.
    When guardrail_verbose is True, root-level 'scanners' is a map id -> { name, direction, ... }; frontend
    uses result.scannerResults[].scannerId (or .id) to look up scanners[id].name for friendly display.
    """
    if not isinstance(guardrail_raw, dict):
        return None
    try:
        # Prefer root-level scanners (verbose response); fallback to result.scanners
        raw_scanners = guardrail_raw.get("scanners")
        if not raw_scanners and isinstance(guardrail_raw.get("result"), dict):
            raw_scanners = guardrail_raw["result"].get("scanners")
        raw_sub = {"result": guardrail_raw.get("result"), "scanners": raw_scanners}
        safe_sub = json.loads(json.dumps(raw_sub, default=str))
        guardrail_result = safe_sub.get("result") or {}
        guardrail_scanners = safe_sub.get("scanners") or {}
        scanners_map = guardrail_scanners
        if isinstance(guardrail_scanners, dict):
            inner = guardrail_scanners.get("scanners")
            if isinstance(inner, dict):
                scanners_map = inner
        return {"result": guardrail_result, "scanners": scanners_map or {}}
    except Exception:
        return None


class GuardrailScanIn(BaseModel):
    message: str
    provider: Optional[str] = None  # 可选，覆盖当前默认 Provider（Inline 模式用）


class OOBChatIn(BaseModel):
    """OOB 旁路模式：前端以 OpenAI 兼容格式发往 Proxy，本接口转发到 OOB_PROXY_URL。"""
    message: str
    stream: bool = False  # 当前 NJS 整段缓冲后返回，暂不支持真正流式；False 时始终 JSON


def _forward_oob_chat(message: str, stream: bool = False) -> Tuple[dict, int]:
    """同步转发到 OOB Proxy，返回 (response_body, status_code)。"""
    if not OOB_PROXY_URL or not LLM_PROVIDER_KEY:
        return {"detail": "OOB_PROXY_URL or LLM_PROVIDER_KEY not configured"}, 400
    url = OOB_PROXY_URL + "/v1/chat/completions"
    body = {
        "model": os.getenv("OOB_MODEL", "deepseek-chat"),
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": message or ""},
        ],
        "stream": stream,
    }
    data = json.dumps(body).encode("utf-8")
    req = UrlRequest(
        url,
        data,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + LLM_PROVIDER_KEY,
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            try:
                out = json.loads(raw)
            except json.JSONDecodeError:
                out = {"raw": raw, "content_type": resp.headers.get("Content-Type", "")}
            return out, resp.status
    except HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
        except Exception:
            err_body = {"detail": str(e.reason) or "Proxy error"}
        return err_body, e.code
    except URLError as e:
        return {"detail": str(e.reason) or "Proxy unreachable"}, 503


async def _forward_oob_chat_stream(message: str):
    """流式转发：上游返回 application/json 时整包返回（BLOCK），否则以 SSE 流式转发（PASS）。"""
    if not OOB_PROXY_URL or not LLM_PROVIDER_KEY:
        return JSONResponse(
            content={"detail": "OOB_PROXY_URL or LLM_PROVIDER_KEY not configured"},
            status_code=400,
        )
    url = OOB_PROXY_URL + "/v1/chat/completions"
    body = {
        "model": os.getenv("OOB_MODEL", "deepseek-chat"),
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": message or ""},
        ],
        "stream": True,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + LLM_PROVIDER_KEY,
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", url, json=body, headers=headers) as r:
                ct = (r.headers.get("content-type") or "").lower()
                if r.status_code < 200 or r.status_code >= 300:
                    raw = await r.aread()
                    return JSONResponse(
                        content={"detail": raw.decode("utf-8", errors="replace")[:2000]},
                        status_code=r.status_code,
                    )
                # 用首块内容判断是否为 SSE，避免上游误设 Content-Type 为 application/json
                first_chunk = b""
                it = r.aiter_bytes()
                try:
                    first_chunk = await it.__anext__()
                except StopAsyncIteration:
                    pass
                def looks_like_sse(data: bytes) -> bool:
                    if not data:
                        return False
                    line = data.split(b"\n", 1)[0].lstrip()
                    return line.startswith(b"data:")

                if looks_like_sse(first_chunk):
                    async def stream_chunks():
                        yield first_chunk
                        async for chunk in it:
                            yield chunk
                    return StreamingResponse(
                        stream_chunks(),
                        media_type="text/event-stream",
                        status_code=r.status_code,
                    )
                raw = first_chunk
                async for chunk in it:
                    raw += chunk
                try:
                    data = json.loads(raw.decode("utf-8"))
                except json.JSONDecodeError:
                    data = {"detail": raw.decode("utf-8", errors="replace")[:2000]}
                return JSONResponse(content=data, status_code=r.status_code)
    except httpx.HTTPStatusError as e:
        try:
            err_body = e.response.json()
        except Exception:
            err_body = {"detail": str(e)}
        return JSONResponse(content=err_body, status_code=e.response.status_code)
    except Exception as e:
        return JSONResponse(
            content={"detail": str(e) or "Proxy error"},
            status_code=503,
        )


@app.post("/api/guardrail-scan")
async def api_guardrail_scan(payload: GuardrailScanIn):
    """Dedicated endpoint for Guardrail Integration view: only calls F5 Guardrail, returns full guardrail JSON for flow visualization."""
    prompt = (payload.message or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="message is required")
    raw_settings = load_settings()
    settings = get_runtime_settings(raw_settings)
    effective_provider = (payload.provider or "").strip() or (raw_settings.get("default_provider") or "").strip() or DEFAULT_PROVIDER
    send_kwargs = build_send_kwargs(verbose=settings.get("guardrail_verbose", False), provider_override=effective_provider or None)
    reply, guardrail_raw = await call_f5_guardrail(prompt, send_kwargs)
    guardrail_payload = _build_guardrail_payload(guardrail_raw)
    return JSONResponse({
        "reply": reply,
        "guardrail": guardrail_payload or {},
    })


@app.post("/api/oob-chat")
async def api_oob_chat(payload: OOBChatIn):
    """OOB 旁路模式：将请求以 OpenAI 兼容格式转发到 NGINX Proxy。stream=True 时 PASS 返回 SSE、BLOCK 返回 JSON；stream=False 时始终返回 JSON。"""
    msg = (payload.message or "").strip()
    if payload.stream:
        return await _forward_oob_chat_stream(msg)
    body, status = await run_in_threadpool(_forward_oob_chat, msg, False)
    return JSONResponse(content=body, status_code=status)


def _get_provider_options() -> list:
    """从环境变量 PROVIDER_OPTIONS（逗号分隔）读取可选 Provider 列表，供前端下拉使用。每次请求时重新加载项目 .env 以便不重启即可生效。"""
    load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)
    raw = (os.getenv("PROVIDER_OPTIONS") or "").strip()
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


@app.get("/api/settings")
async def get_settings():
    out = dict(load_settings())
    out["provider_options"] = _get_provider_options()
    return out

@app.post("/api/settings")
async def post_settings(payload: dict = Body(default=None)):
    merged = load_settings()
    if isinstance(payload, dict) and payload:
        merged.update(payload)
    merged = get_runtime_settings(merged)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    return {"status": "ok", "settings": merged}