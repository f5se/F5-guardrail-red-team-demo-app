import os
import time
import json
import re
from collections import defaultdict, deque
from typing import Deque, Dict, List, Optional, Tuple

from dotenv import load_dotenv
load_dotenv()  # 从项目目录 .env 加载环境变量

# 仅 Hugging Face 模型下载走代理；CalypsoAI 不走代理。
# 在 .env 中设置 HF_PROXY 或 PROXY，例如: HF_PROXY=http://127.0.0.1:7890
# -----------------------------
HF_PROXY = os.getenv("HF_PROXY") or os.getenv("PROXY")

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from calypsoai import CalypsoAI
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

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


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


# -----------------------------
# UI Routes
# -----------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
async def health():
    return {"status": "ok", "ts": int(time.time())}


# -----------------------------
# Helpers
# -----------------------------
def build_send_kwargs() -> dict:
    if CALYPSOAI_PROJECT_ID:
        # The SDK argument is often 'project_id' or 'project'. 
        # Based on your docs, 'project' is the correct argument name.
        return {"project": CALYPSOAI_PROJECT_ID}

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
    "kb_dir": "./enterprise_kb",
    "agent_max_steps": 4,
    "agent_debug_enabled": False,
    "kb_top_k": 3,
    "kb_allowed_extensions": ".txt,.md,.json,.csv",
    "kb_max_file_chars": 8000,
    "kb_max_result_chars": 5000,
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
        "kb_dir": str(raw.get("kb_dir") or "./enterprise_kb"),
        "agent_max_steps": to_int(raw.get("agent_max_steps", 4), 4, 1, 8),
        "agent_debug_enabled": to_bool(raw.get("agent_debug_enabled", False)),
        "kb_top_k": to_int(raw.get("kb_top_k", 3), 3, 1, 8),
        "kb_allowed_extensions": normalize_extensions(raw.get("kb_allowed_extensions", ".txt,.md,.json,.csv")),
        "kb_max_file_chars": to_int(raw.get("kb_max_file_chars", 8000), 8000, 500, 50000),
        "kb_max_result_chars": to_int(raw.get("kb_max_result_chars", 5000), 5000, 500, 20000),
    }

def format_guardrail_reply(data: dict) -> str:
    guardrail_result = (data.get("result") or {})
    outcome = guardrail_result.get("outcome")
    if outcome == "cleared":
        return guardrail_result.get("response", "") or "(empty response)"
    calypso_type = str(data.get("type", "")).lower()
    label = "Response" if calypso_type == "response" else "Prompt"
    return (
        f"{label} Rejected\n\n"
        f"The requested {label} was rejected by F5 AI Guardrail because it violated "
        "the company's AI security policy."
    )

async def call_f5_guardrail(prompt_to_send: str, send_kwargs: dict) -> Tuple[str, dict]:
    try:
        result = await run_in_threadpool(cai.prompts.send, prompt_to_send, **send_kwargs)
        data = result.model_dump()
    except Exception as e:
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
        outcome = ((data.get("result") or {}).get("outcome") or "").lower()
        agent_debug_log(settings, f"skill_loop step={step} outcome={outcome or 'unknown'}")
        if outcome != "cleared":
            agent_debug_log(settings, f"skill_loop stop_on_guardrail_reject step={step}")
            return {
                "reply": reply,
                "trace": trace,
                "tool_calls": tool_calls,
                "skill_used": len(tool_calls) > 0,
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
    send_kwargs = build_send_kwargs()

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
    else:
        agent_debug_log(settings, "api_chat mode=plain_guardrail")
        reply, _ = await call_f5_guardrail(prompt_to_send, send_kwargs)

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
    # LOCAL ENGINE DETECTION
    # ======================
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

    return JSONResponse(
        {
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
    )

@app.get("/api/settings")
async def get_settings():
    return load_settings()

@app.post("/api/settings")
async def post_settings(payload: dict):
    merged = load_settings()
    if isinstance(payload, dict):
        merged.update(payload)
    merged = get_runtime_settings(merged)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(merged, f, indent=2)
    return {"status":"ok", "settings": merged}