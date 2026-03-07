import os
import time
import json
from collections import defaultdict, deque
from typing import Deque, Dict, List, Literal, Optional

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

SETTINGS_FILE = "settings.json"

DEFAULT_SETTINGS = {
    "patterns": "ignore:3\nsystem:3\nprompt:2",
    "heuristic_threshold": 10,
    "toxic_threshold": 0.75,
    "pi_threshold": 0.7
}

def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return DEFAULT_SETTINGS
    with open(SETTINGS_FILE) as f:
        return json.load(f)

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

    # Call Calypso Guardrail
    try:
        #result = cai.prompts.send(prompt_to_send, **send_kwargs)
        result = await run_in_threadpool(cai.prompts.send, prompt_to_send, **send_kwargs)
        data = result.model_dump()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to call Guardrail: {e}")

    guardrail_result = (data.get("result") or {})
    outcome = guardrail_result.get("outcome")
    
    if outcome == "cleared":
        reply = guardrail_result.get("response", "") or "(empty response)"
    else:
        calypso_type = str(data.get("type", "")).lower()
        label = "Response" if calypso_type == "response" else "Prompt"
        reply = (
            f"{label} Rejected\n\n"
            f"The requested {label} was rejected by F5 AI Guardrail because it violated "
            "the company's AI security policy."
        )

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
    settings = load_settings()
    
    # FORCE TYPE SAFETY
    heuristic_threshold = int(settings.get("heuristic_threshold", 10))
    toxic_threshold = float(settings.get("toxic_threshold", 0.75))
    pi_threshold = float(settings.get("pi_threshold", 0.7))
    
    pattern_map = parse_patterns(settings["patterns"])
    msg_lower = user_message.lower()

    # Pattern Engine
    matched_keyword = next((k for k in pattern_map if k in msg_lower), None)

    # Heuristic Engine
    heuristic_score = sum(
        pattern_map[k] for k in pattern_map if k in msg_lower
    )
    
    # Toxic Engine
    try:
        # Run blocking model in a separate thread
        tox_results = await run_in_threadpool(tox_model, user_message)
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
        pi_results = await run_in_threadpool(pi_model, user_message)
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
        }
    )

@app.get("/api/settings")
async def get_settings():
    return load_settings()

@app.post("/api/settings")
async def post_settings(payload: dict):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(payload, f, indent=2)
    return {"status":"ok"}