import asyncio
import os
import time
import json
import re
import ipaddress
import hmac
import base64
import hashlib
import secrets
import threading
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
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

from fastapi import FastAPI, Request, HTTPException, Body, Query
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.concurrency import run_in_threadpool
from starlette import status
from pydantic import BaseModel
import httpx

from calypsoai import CalypsoAI
import calypsoai.datatypes as cai_dt
from transformers import pipeline
try:
    import geoip2.database
except Exception:
    geoip2 = None

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
PROMPT_INJECTION_SCANNER_ID = (os.getenv("PROMPT_INJECTION_SCANNER_ID") or "").strip()
PROMPT_INJECTION_DEFAULT_VERSION = (os.getenv("PROMPT_INJECTION_DEFAULT_VERSION") or "").strip()
# Hugging Face：用于模型下载，可提升速率并避免匿名 API 限制。在 .env 中设置 HF_TOKEN=hf_xxx
HF_TOKEN = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")

SLIDING_WINDOW_MAX_TURNS = int(os.getenv("SLIDING_WINDOW_MAX_TURNS", "8"))
SLIDING_WINDOW_MAX_CHARS = int(os.getenv("SLIDING_WINDOW_MAX_CHARS", "2000"))

CONVERSATION_TTL_SECONDS = int(os.getenv("CONVERSATION_TTL_SECONDS", "120"))  # 2 minutes
GUARDRAIL_TIMEOUT_SECONDS = float(os.getenv("GUARDRAIL_TIMEOUT_SECONDS", "5"))


def _env_int_bounded(name: str, default: int, lo: int, hi: int) -> int:
    try:
        v = int(str(os.getenv(name, str(default))).strip())
    except ValueError:
        v = default
    return max(lo, min(v, hi))


# Enterprise KB / SaaS scanner 漂移告警：前端轮询间隔（秒），默认 5 分钟
SCANNER_DRIFT_POLL_SECONDS = _env_int_bounded("SCANNER_DRIFT_POLL_SECONDS", 300, 30, 3600)

# OOB 旁路模式：Proxy(NGINX) 地址与 LLM Provider API Key
OOB_PROXY_URL = (os.getenv("OOB_PROXY_URL") or "").rstrip("/")
LLM_PROVIDER_KEY = os.getenv("LLM_PROVIDER_KEY") or ""
LLM_PROVIDER_URL = (os.getenv("LLM_PROVIDER_URL") or "").rstrip("/")
LLM_PROVIDER_KEY_DIRECT = os.getenv("LLM_PROVIDER_KEY_Direct") or ""
LLM_PROVIDER_MODEL = os.getenv("LLM_PROVIDER_MODEL") or ""

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
conversation_owners: Dict[str, str] = {}

# -----------------------------
# Models
# -----------------------------
class ChatIn(BaseModel):
    message: str
    conversation_id: str
    multi_turn: bool = False
    provider: Optional[str] = None  # 可选，覆盖当前默认 Provider（主 Chat/Agent 用）
    agent_skill_enabled: Optional[bool] = None  # 会话临时覆盖，不落盘
    f5_guardrail_only: Optional[bool] = None  # 会话临时覆盖，不落盘


# -----------------------------
# UI Routes
# -----------------------------
@app.middleware("http")
async def auth_guard(request: Request, call_next):
    path = request.url.path
    public_prefixes = ("/static/", "/redteam-report/")
    public_paths = {"/health", "/login", "/api/login"}
    if path in public_paths or any(path.startswith(p) for p in public_prefixes):
        return await call_next(request)

    session = get_current_session(request)
    if not session:
        if path.startswith("/api/"):
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    touch_session_activity(session["session_id"], path)
    request.state.session_id = session["session_id"]
    request.state.username = session["username"]
    return await call_next(request)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if get_current_session(request):
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/api/login")
async def api_login(request: Request, payload: dict = Body(default=None)):
    username = str((payload or {}).get("username") or "").strip()
    password = str((payload or {}).get("password") or "")
    if not username or not password:
        raise HTTPException(status_code=400, detail="username and password are required")

    client_key = _login_client_key(request, username)
    remain = _check_login_lock(client_key)
    if remain > 0:
        raise HTTPException(status_code=429, detail=f"too many failed attempts, retry after {remain}s")

    structured = load_structured_settings()
    users = get_enabled_users(structured)
    user_item = users.get(username)
    if not user_item or not verify_password(password, user_item.get("password_hash", "")):
        _register_login_failure(client_key)
        raise HTTPException(status_code=401, detail="invalid username or password")

    _clear_login_failure(client_key)
    upsert_user_settings(username)
    ttl = to_int(structured.get("auth", {}).get("session_ttl_seconds", 86400), 86400, 300, 604800)
    sid = create_session(username, ttl, _client_ip(request))
    resp = JSONResponse({"status": "ok", "username": username})
    resp.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=sid,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=ttl,
    )
    return resp


@app.post("/api/logout")
async def api_logout(request: Request):
    sid = request.cookies.get(SESSION_COOKIE_NAME)
    if sid:
        with SESSIONS_LOCK:
            SESSIONS.pop(sid, None)
    resp = JSONResponse({"status": "ok"})
    resp.delete_cookie(SESSION_COOKIE_NAME)
    return resp


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    attack_presets = load_attack_presets()
    guardrail_integration_presets = load_guardrail_integration_presets()
    username = require_user(request)
    raw_settings = get_effective_raw_settings(username)
    effective_provider = (str(raw_settings.get("default_provider", "") or "").strip() or (DEFAULT_PROVIDER or "").strip())
    chat_subtitle = f"F5 AI Demo Chatbot · Connected to Backend {effective_provider}" if effective_provider else "F5 AI Demo Chatbot · Connected to Backend LLM"
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "attack_presets_json": json.dumps(attack_presets, ensure_ascii=False),
            "guardrail_integration_presets_json": json.dumps(guardrail_integration_presets, ensure_ascii=False),
            "chat_subtitle": chat_subtitle,
        },
    )


@app.get("/health")
async def health():
    return {"status": "ok", "ts": int(time.time())}


@app.get("/api/test-guide")
async def api_test_guide():
    """Return docs/test-guide.md as raw markdown text for frontend rendering."""
    path = os.path.join(BASE_DIR, "docs", "test-guide.md")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="test-guide.md not found")
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"failed to read test-guide.md: {e}")
    return PlainTextResponse(content, media_type="text/markdown; charset=utf-8")


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
LOGIN_ACTIVITY_FILE = os.path.join(BASE_DIR, "login_activity.log")
GEOIP_DB_FILE = os.path.join(BASE_DIR, "static", "ip", "GeoLite2-City.mmdb")
print(f"[CONFIG] SETTINGS_FILE={SETTINGS_FILE}")

DEFAULT_SETTINGS = {
    "patterns": "ignore:3\nsystem:3\nprompt:2",
    "heuristic_threshold": 6,
    "toxic_threshold": 0.75,
    "pi_threshold": 0.7,
    "multi_turn_enabled": False,
    "agent_skill_enabled": False,
    "f5_guardrail_only": False,
    "debug_guardrail_raw_enabled": False,
    "guardrail_verbose": False,
    "guardrail_timeout_seconds": GUARDRAIL_TIMEOUT_SECONDS,
    "kb_dir": "./enterprise_kb",
    "agent_max_steps": 4,
    "agent_debug_enabled": False,
    "kb_top_k": 3,
    "kb_allowed_extensions": ".txt,.md,.json,.csv",
    "kb_max_file_chars": 8000,
    "kb_max_result_chars": 5000,
    "default_provider": "",  # 前端可选；空则用 env DEFAULT_PROVIDER
}
NEW_USER_PATTERNS_FALLBACK = "ignore:3\nsystem:3\nprompt:2\n忽略:3\n系统提示词:3\n忘记:2\n角色:4\n"

USER_SCOPED_KEYS = {
    "patterns",
    "heuristic_threshold",
    "toxic_threshold",
    "pi_threshold",
    "multi_turn_enabled",
    "agent_skill_enabled",
    "f5_guardrail_only",
    "debug_guardrail_raw_enabled",
    "default_provider",
}
GLOBAL_SCOPED_KEYS = {k for k in DEFAULT_SETTINGS if k not in USER_SCOPED_KEYS}
SETTINGS_LOCK = threading.Lock()
SESSIONS_LOCK = threading.Lock()
LOGIN_GUARD_LOCK = threading.Lock()
SESSIONS: Dict[str, dict] = {}
ACTIVITY_GAP_SECONDS = 30
ACTIVITY_THRESHOLD_SECONDS = 120
SESSION_COOKIE_NAME = "aigr_session"
SESSION_IDLE_TIMEOUT_SECONDS = 20 * 60
BEIJING_TZ = timezone(timedelta(hours=8))
AUDIT_TRIGGER_PATHS = {
    "/api/chat",
    "/api/guardrail-scan",
    "/api/oob-chat",
    "/api/chat-direct",
}
LOGIN_FAIL_LIMIT = 5
LOGIN_LOCK_SECONDS = 300
LOGIN_ATTEMPTS: Dict[str, dict] = {}
GEOIP_LOOKUP_CACHE: Dict[str, str] = {}


def _resolve_city_by_ip(ip_raw: str) -> str:
    ip_text = str(ip_raw or "").strip()
    if not ip_text:
        return "Unknown"
    if ip_text in GEOIP_LOOKUP_CACHE:
        return GEOIP_LOOKUP_CACHE[ip_text]
    try:
        ip_obj = ipaddress.ip_address(ip_text)
        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local:
            city_name = "Local Network"
            GEOIP_LOOKUP_CACHE[ip_text] = city_name
            return city_name
    except Exception:
        GEOIP_LOOKUP_CACHE[ip_text] = "Unknown"
        return "Unknown"
    if geoip2 is None:
        GEOIP_LOOKUP_CACHE[ip_text] = "Unknown"
        return "Unknown"
    if not os.path.exists(GEOIP_DB_FILE):
        GEOIP_LOOKUP_CACHE[ip_text] = "Unknown"
        return "Unknown"
    try:
        with geoip2.database.Reader(GEOIP_DB_FILE) as reader:
            city_resp = reader.city(ip_text)
        city_name = (
            (city_resp.city.names or {}).get("zh-CN")
            or city_resp.city.name
            or (city_resp.country.names or {}).get("zh-CN")
            or city_resp.country.name
            or "Unknown"
        )
        city_name = str(city_name).strip() or "Unknown"
    except Exception:
        city_name = "Unknown"
    GEOIP_LOOKUP_CACHE[ip_text] = city_name
    return city_name


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _client_ip(request: Request) -> str:
    xff = (request.headers.get("x-forwarded-for") or "").strip()
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    xrip = (request.headers.get("x-real-ip") or "").strip()
    if xrip:
        return xrip
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _login_client_key(request: Request, username: str) -> str:
    # 使用 username + IP + UA 组合，尽量在共享公网IP场景下减少误伤。
    ua = (request.headers.get("user-agent") or "").strip().lower()
    ip = _client_ip(request)
    return f"{username.lower()}|{ip}|{ua}"


def _check_login_lock(client_key: str) -> int:
    now = time.time()
    with LOGIN_GUARD_LOCK:
        rec = LOGIN_ATTEMPTS.get(client_key)
        if not rec:
            return 0
        lock_until = float(rec.get("lock_until", 0))
        if lock_until > now:
            return int(lock_until - now)
        if lock_until and lock_until <= now:
            LOGIN_ATTEMPTS.pop(client_key, None)
            return 0
        return 0


def _register_login_failure(client_key: str):
    now = time.time()
    with LOGIN_GUARD_LOCK:
        rec = LOGIN_ATTEMPTS.get(client_key) or {"count": 0, "first_ts": now, "lock_until": 0}
        lock_until = float(rec.get("lock_until", 0))
        if lock_until > now:
            LOGIN_ATTEMPTS[client_key] = rec
            return
        first_ts = float(rec.get("first_ts", now))
        # 失败窗口按 5 分钟滚动统计；超窗则重置计数
        if now - first_ts > LOGIN_LOCK_SECONDS:
            rec = {"count": 0, "first_ts": now, "lock_until": 0}
        rec["count"] = int(rec.get("count", 0)) + 1
        if rec["count"] >= LOGIN_FAIL_LIMIT:
            rec["lock_until"] = now + LOGIN_LOCK_SECONDS
            rec["count"] = 0
            rec["first_ts"] = now
        LOGIN_ATTEMPTS[client_key] = rec


def _clear_login_failure(client_key: str):
    with LOGIN_GUARD_LOCK:
        LOGIN_ATTEMPTS.pop(client_key, None)


def _pbkdf2_hash_password(password: str, salt: str, iterations: int) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    return base64.urlsafe_b64encode(dk).decode("ascii").rstrip("=")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algo, iter_s, salt, digest = str(password_hash or "").split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iter_s)
        expected = _pbkdf2_hash_password(password, salt, iterations)
        return hmac.compare_digest(expected, digest)
    except Exception:
        return False


def make_hash_entry(username: str, password: str, *, iterations: int = 120000) -> dict:
    salt = base64.urlsafe_b64encode(secrets.token_bytes(12)).decode("ascii").rstrip("=")
    return {
        "username": username,
        "password_hash": f"pbkdf2_sha256${iterations}${salt}${_pbkdf2_hash_password(password, salt, iterations)}",
        "enabled": True,
    }


def default_structured_settings() -> dict:
    return {
        "auth": {
            "users": [make_hash_entry("admin", "admin123456")],
            "session_ttl_seconds": 86400,
        },
        "global_settings": {k: DEFAULT_SETTINGS[k] for k in GLOBAL_SCOPED_KEYS},
        "user_settings": {},
    }


def normalize_structured_settings(loaded: Optional[dict]) -> dict:
    baseline = default_structured_settings()
    if not isinstance(loaded, dict):
        return baseline

    is_new_schema = any(k in loaded for k in ("auth", "global_settings", "user_settings"))
    if not is_new_schema:
        global_settings = {k: loaded.get(k, DEFAULT_SETTINGS[k]) for k in GLOBAL_SCOPED_KEYS}
        default_user = {k: loaded.get(k, DEFAULT_SETTINGS[k]) for k in USER_SCOPED_KEYS}
        return {
            "auth": baseline["auth"],
            "global_settings": global_settings,
            "user_settings": {"admin": default_user},
        }

    auth = loaded.get("auth") if isinstance(loaded.get("auth"), dict) else {}
    global_settings = loaded.get("global_settings") if isinstance(loaded.get("global_settings"), dict) else {}
    user_settings = loaded.get("user_settings") if isinstance(loaded.get("user_settings"), dict) else {}

    users = auth.get("users")
    if not isinstance(users, list) or not users:
        users = baseline["auth"]["users"]

    merged_auth = {
        "users": users,
        "session_ttl_seconds": to_int(auth.get("session_ttl_seconds", 86400), 86400, 300, 604800),
    }
    merged_global = {k: global_settings.get(k, DEFAULT_SETTINGS[k]) for k in GLOBAL_SCOPED_KEYS}
    normalized_user_settings = {}
    for username, val in user_settings.items():
        if not isinstance(val, dict):
            continue
        normalized_user_settings[str(username)] = {k: val.get(k, DEFAULT_SETTINGS[k]) for k in USER_SCOPED_KEYS}

    return {
        "auth": merged_auth,
        "global_settings": merged_global,
        "user_settings": normalized_user_settings,
    }


def _atomic_write_json(path: str, data: dict):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def load_structured_settings() -> dict:
    if not os.path.exists(SETTINGS_FILE):
        structured = default_structured_settings()
        with SETTINGS_LOCK:
            _atomic_write_json(SETTINGS_FILE, structured)
        return structured
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    return normalize_structured_settings(loaded)


def save_structured_settings(data: dict):
    with SETTINGS_LOCK:
        _atomic_write_json(SETTINGS_FILE, data)


def get_effective_raw_settings(username: Optional[str]) -> dict:
    structured = load_structured_settings()
    merged = dict(structured["global_settings"])
    if username:
        user_part = structured["user_settings"].get(username, {})
        for k in USER_SCOPED_KEYS:
            if k in user_part:
                merged[k] = user_part[k]
    return merged


def _new_user_settings_from_template(structured: dict) -> dict:
    new_user_settings = {k: DEFAULT_SETTINGS[k] for k in USER_SCOPED_KEYS}
    admin_patterns = None
    user_settings = structured.get("user_settings", {})
    if isinstance(user_settings, dict):
        admin = user_settings.get("admin")
        if isinstance(admin, dict):
            admin_patterns = admin.get("patterns")
    if isinstance(admin_patterns, str) and admin_patterns.strip():
        new_user_settings["patterns"] = admin_patterns
    else:
        new_user_settings["patterns"] = NEW_USER_PATTERNS_FALLBACK
    return new_user_settings


def upsert_user_settings(username: str):
    structured = load_structured_settings()
    if username not in structured["user_settings"]:
        structured["user_settings"][username] = _new_user_settings_from_template(structured)
        save_structured_settings(structured)
    return structured


def get_enabled_users(structured: dict) -> Dict[str, dict]:
    users_map: Dict[str, dict] = {}
    users = structured.get("auth", {}).get("users", [])
    if not isinstance(users, list):
        return users_map
    for item in users:
        if not isinstance(item, dict):
            continue
        username = str(item.get("username") or "").strip()
        if not username:
            continue
        if item.get("enabled", True) is False:
            continue
        users_map[username] = item
    return users_map


def create_session(username: str, ttl_seconds: int, client_ip: str) -> str:
    sid = secrets.token_urlsafe(24)
    now = time.time()
    with SESSIONS_LOCK:
        SESSIONS[sid] = {
            "username": username,
            "created_at": now,
            "last_seen": now,
            "active_seconds": 0.0,
            "logged_120s": False,
            "expires_at": now + ttl_seconds,
            "login_iso": _utc_now_iso(),
            "client_ip": client_ip or "unknown",
        }
    return sid


def append_login_activity(username: str, login_iso: str, session_id: str, client_ip: str):
    rec = {
        "username": username,
        "login_datetime": login_iso,
        "threshold_reached_datetime": _utc_now_iso(),
        "session_id": session_id,
        "client_ip": client_ip or "unknown",
    }
    line = json.dumps(rec, ensure_ascii=False)
    with open(LOGIN_ACTIVITY_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def touch_session_activity(session_id: str, request_path: str = ""):
    now = time.time()
    with SESSIONS_LOCK:
        sess = SESSIONS.get(session_id)
        if not sess:
            return
        if now > sess["expires_at"]:
            del SESSIONS[session_id]
            return
        idle = now - sess["last_seen"]
        if idle > SESSION_IDLE_TIMEOUT_SECONDS:
            del SESSIONS[session_id]
            return
        sess["last_seen"] = now

        # 新规则：会话存活期间（未超时/未退出），命中指定API任意一次即记录一次。
        if (not sess["logged_120s"]) and request_path in AUDIT_TRIGGER_PATHS:
            sess["logged_120s"] = True
            append_login_activity(
                sess["username"],
                sess["login_iso"],
                session_id,
                str(sess.get("client_ip") or "unknown"),
            )


def get_current_session(request: Request) -> Optional[dict]:
    sid = request.cookies.get(SESSION_COOKIE_NAME)
    if not sid:
        return None
    with SESSIONS_LOCK:
        sess = SESSIONS.get(sid)
        if not sess:
            return None
        if time.time() > sess["expires_at"]:
            del SESSIONS[sid]
            return None
        if (time.time() - sess["last_seen"]) > SESSION_IDLE_TIMEOUT_SECONDS:
            del SESSIONS[sid]
            return None
        return {"session_id": sid, **sess}


def require_user(request: Request) -> str:
    if getattr(request.state, "username", None):
        return request.state.username
    sess = get_current_session(request)
    if not sess:
        raise HTTPException(status_code=401, detail="unauthorized")
    touch_session_activity(sess["session_id"], request.url.path)
    request.state.session_id = sess["session_id"]
    request.state.username = sess["username"]
    return sess["username"]

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
        "heuristic_threshold": to_int(raw.get("heuristic_threshold", DEFAULT_SETTINGS["heuristic_threshold"]), DEFAULT_SETTINGS["heuristic_threshold"], 1, 100),
        "toxic_threshold": to_float(raw.get("toxic_threshold", 0.75), 0.75, 0.0, 1.0),
        "pi_threshold": to_float(raw.get("pi_threshold", 0.7), 0.7, 0.0, 1.0),
        "multi_turn_enabled": to_bool(raw.get("multi_turn_enabled", DEFAULT_SETTINGS["multi_turn_enabled"])),
        "agent_skill_enabled": to_bool(raw.get("agent_skill_enabled", False)),
        "f5_guardrail_only": to_bool(raw.get("f5_guardrail_only", False)),
        "debug_guardrail_raw_enabled": to_bool(raw.get("debug_guardrail_raw_enabled", False)),
        "guardrail_verbose": to_bool(raw.get("guardrail_verbose", False)),
        "guardrail_timeout_seconds": to_float(raw.get("guardrail_timeout_seconds", GUARDRAIL_TIMEOUT_SECONDS), GUARDRAIL_TIMEOUT_SECONDS, 1.0, 120.0),
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


async def call_f5_guardrail(prompt_to_send: str, send_kwargs: dict, *, timeout_seconds: float) -> Tuple[str, dict]:
    _guardrail_debug("call_f5_guardrail: 即将发起请求（进入线程池前）")
    try:
        # send_kwargs 会被 _call_f5_guardrail_sync  pop 掉 verbose，复制一份避免影响调用方
        kwargs = dict(send_kwargs)
        result = await asyncio.wait_for(
            run_in_threadpool(_call_f5_guardrail_sync, prompt_to_send, kwargs),
            timeout=timeout_seconds,
        )
        _guardrail_debug("call_f5_guardrail: 已收到服务端完整响应")
        data = result if isinstance(result, dict) else result.model_dump()
    except TimeoutError:
        _guardrail_debug(f"call_f5_guardrail: 请求超时 timeout_seconds={timeout_seconds}")
        raise HTTPException(
            status_code=504,
            detail=f"Guardrail request timed out after {timeout_seconds:.1f}s",
        )
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
        reply, data = await call_f5_guardrail(
            prompt, send_kwargs, timeout_seconds=settings["guardrail_timeout_seconds"]
        )
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


async def _post_direct_chat_completions(
    messages: List[dict],
    *,
    base_url: str,
    api_key: str,
    model: str,
    timeout: float = 120.0,
) -> str:
    """POST OpenAI-compatible chat/completions; return assistant text."""
    url = base_url + "/chat/completions"
    body = {"model": model, "messages": messages, "stream": False}
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + api_key}
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, json=body, headers=headers)
    if r.status_code < 200 or r.status_code >= 300:
        err_text = r.text[:2000] if isinstance(r.text, str) else ""
        raise HTTPException(status_code=r.status_code, detail=err_text or "Direct provider request failed")
    return _extract_openai_reply(r.json())


async def run_agent_skill_loop_direct(
    user_input: str,
    settings: dict,
    *,
    base_url: str,
    api_key: str,
    model: str,
) -> dict:
    """
    Same ReAct-style tool loop as run_agent_skill_loop, but each planner step calls the
    direct OpenAI-compatible provider (no F5 Guardrail).
    """
    max_steps = settings["agent_max_steps"]
    tool_defs = get_all_tool_definitions()
    scratchpad_entries: List[str] = []
    trace: List[dict] = []
    tool_calls: List[dict] = []
    agent_debug_log(
        settings,
        f"direct_skill_loop start max_steps={max_steps} user_input_chars={len(user_input)}",
    )

    for step in range(1, max_steps + 1):
        prompt = build_agent_prompt(
            user_input=user_input,
            scratchpad="\n".join(scratchpad_entries),
            tool_defs=tool_defs,
            step=step,
            max_steps=max_steps,
        )
        messages = [{"role": "user", "content": prompt}]
        reply = await _post_direct_chat_completions(
            messages, base_url=base_url, api_key=api_key, model=model
        )
        agent_debug_log(settings, f"direct_skill_loop step={step} reply_chars={len(reply or '')}")

        obj, parse_err = extract_json_object(reply)
        if parse_err:
            agent_debug_log(settings, f"direct_skill_loop parse_error step={step} err={parse_err}")
            trace.append({"step": step, "event": "parse_error", "detail": parse_err})
            scratchpad_entries.append(
                f"Observation(parse_error): {parse_err}. raw_reply={reply[:400]}"
            )
            continue

        event_type = str(obj.get("type", "")).lower()
        if event_type == "final":
            answer = str(obj.get("answer", "")).strip() or "(empty response)"
            agent_debug_log(settings, f"direct_skill_loop final step={step} answer_chars={len(answer)}")
            trace.append({"step": step, "event": "final"})
            return {
                "reply": answer,
                "trace": trace,
                "tool_calls": tool_calls,
                "skill_used": len(tool_calls) > 0,
            }

        if event_type != "tool_call":
            agent_debug_log(
                settings,
                f"direct_skill_loop invalid_event step={step} event_type={event_type or 'missing'}",
            )
            trace.append({"step": step, "event": "invalid_event", "detail": event_type or "missing type"})
            scratchpad_entries.append(f"Observation(error): invalid event type={event_type or 'missing'}")
            continue

        tool_name = str(obj.get("name", "")).strip()
        arguments = obj.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {}

        trace.append({"step": step, "event": "tool_call", "name": tool_name})
        tool_calls.append({"step": step, "name": tool_name, "arguments": arguments})
        agent_debug_log(settings, f"direct_skill_loop tool_call step={step} name={tool_name}")

        tool_result = dispatch_tool(tool_name, arguments, settings)

        compact_result = json.dumps(tool_result, ensure_ascii=False)
        agent_debug_log(
            settings,
            f"direct_skill_loop tool_result step={step} ok={tool_result.get('ok', False)}",
        )
        scratchpad_entries.append(
            f"Action: {tool_name}({json.dumps(arguments, ensure_ascii=False)})\n"
            f"Observation: {compact_result[:1500]}"
        )

    fallback = "I could not finish the tool reasoning loop in time. Please retry with a more specific request."
    agent_debug_log(settings, "direct_skill_loop fallback_max_steps_reached")
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
async def api_chat(request: Request, payload: ChatIn):
    user_message = (payload.message or "").strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Message is required")

    conversation_id = (payload.conversation_id or "").strip()
    if not conversation_id:
        raise HTTPException(status_code=400, detail="conversation_id is required")

    username = require_user(request)
    owner = conversation_owners.get(conversation_id)
    if owner and owner != username:
        raise HTTPException(status_code=403, detail="conversation_id belongs to another user")
    conversation_owners[conversation_id] = username

    raw_settings = get_effective_raw_settings(username)
    settings = get_runtime_settings(raw_settings)
    if isinstance(payload.agent_skill_enabled, bool):
        settings["agent_skill_enabled"] = payload.agent_skill_enabled
    if isinstance(payload.f5_guardrail_only, bool):
        settings["f5_guardrail_only"] = payload.f5_guardrail_only
    agent_debug_log(
        settings,
        f"api_chat start conversation_id={conversation_id} multi_turn={payload.multi_turn} "
        f"agent_skill={settings.get('agent_skill_enabled')} f5_only={settings.get('f5_guardrail_only')}",
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
        reply, guardrail_raw = await call_f5_guardrail(
            prompt_to_send, send_kwargs, timeout_seconds=settings["guardrail_timeout_seconds"]
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
        conversation_owners.pop(conversation_id, None)

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


class DirectChatIn(BaseModel):
    """Chat direct mode: OpenAI-compatible request body."""
    messages: List[dict]
    stream: bool = False
    agent_skill_enabled: Optional[bool] = None  # 与主 Chat 一致：会话临时覆盖 Enterprise KB Skill


class AgentSkillSyncIn(BaseModel):
    enabled: bool


def _extract_last_user_text_from_messages(messages: List[dict]) -> str:
    """取 messages 中最后一条 user 的文本，供直连 Agent 模式使用。"""
    for m in reversed(messages or []):
        if not isinstance(m, dict):
            continue
        if str(m.get("role") or "").lower() != "user":
            continue
        content = m.get("content")
        if isinstance(content, str):
            return content.strip()
        if content is None:
            return ""
        return str(content).strip()
    return ""


def _get_direct_provider_config() -> Tuple[str, str, str]:
    """Reload .env on each request so direct config can change without restart."""
    load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)
    base_url = (os.getenv("LLM_PROVIDER_URL") or LLM_PROVIDER_URL or "").strip().rstrip("/")
    # 兼容多种命名：LLM_PROVIDER_KEY_Direct / LLM_PROVIDER_KEY_DIRECT；并兜底读取 .env 原始文本
    api_key = (
        os.getenv("LLM_PROVIDER_KEY_Direct")
        or os.getenv("LLM_PROVIDER_KEY_DIRECT")
        or LLM_PROVIDER_KEY_DIRECT
        or ""
    ).strip()
    model = (os.getenv("LLM_PROVIDER_MODEL") or LLM_PROVIDER_MODEL or "").strip()
    if not api_key:
        env_path = os.path.join(BASE_DIR, ".env")
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if not s or s.startswith("#") or "=" not in s:
                        continue
                    k, v = s.split("=", 1)
                    key_name = k.strip()
                    if key_name in ("LLM_PROVIDER_KEY_Direct", "LLM_PROVIDER_KEY_DIRECT"):
                        api_key = v.strip()
                        break
        except Exception:
            pass
    return base_url, api_key, model


def _sync_prompt_injection_scanner_for_agent_skill(agent_skill_enabled: bool) -> dict:
    """Sync SaaS scanner state with Enterprise KB Skill toggle.

    Rule:
    - Enterprise KB Skill ON  -> disable scanner
    - Enterprise KB Skill OFF -> enable scanner
    """
    if not CALYPSOAI_PROJECT_ID:
        raise HTTPException(status_code=500, detail="CALYPSOAI_PROJECT_ID is not set")
    if not PROMPT_INJECTION_SCANNER_ID:
        raise HTTPException(status_code=500, detail="PROMPT_INJECTION_SCANNER_ID is not set")

    scanner_enabled = not bool(agent_skill_enabled)
    scanner_cfg = {"id": PROMPT_INJECTION_SCANNER_ID, "enabled": scanner_enabled}
    if PROMPT_INJECTION_DEFAULT_VERSION:
        scanner_cfg["version"] = PROMPT_INJECTION_DEFAULT_VERSION

    body = {"config": {"scanners": [scanner_cfg]}}
    try:
        cai.client.projects.patchProject(project=CALYPSOAI_PROJECT_ID, body=body)
        cfg_map = cai.projects.getScanners(CALYPSOAI_PROJECT_ID).configs or {}
        cfg = cfg_map.get(PROMPT_INJECTION_SCANNER_ID)
        verified_enabled = None if cfg is None else getattr(cfg, "enabled", None)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to sync SaaS scanner: {e}")

    return {
        "project_id": CALYPSOAI_PROJECT_ID,
        "scanner_id": PROMPT_INJECTION_SCANNER_ID,
        "scanner_enabled_target": scanner_enabled,
        "scanner_enabled_verified": verified_enabled,
        "version": PROMPT_INJECTION_DEFAULT_VERSION or None,
    }


def _scanner_id_in_mapping(sid: str, mapping: Optional[dict]) -> bool:
    if not isinstance(mapping, dict) or not sid:
        return False
    if sid in mapping:
        return True
    return any(str(k) == sid for k in mapping)


def _read_prompt_injection_scanner_saas_state() -> Tuple[Optional[bool], Optional[str]]:
    """Read current Prompt Injection scanner enabled flag from SaaS project (read-only).

    Calypso often **omits** a scanner from `configs` (and from `scanners`) when it is disabled
    for the project — absence means *not active*, not a read error.
    """
    if not CALYPSOAI_PROJECT_ID or not PROMPT_INJECTION_SCANNER_ID:
        return None, "missing_project_or_scanner_env"
    try:
        ps = cai.projects.getScanners(CALYPSOAI_PROJECT_ID)
        cfg_map = ps.configs or {}
        sid = PROMPT_INJECTION_SCANNER_ID
        cfg = cfg_map.get(sid)
        if cfg is None:
            for k, v in cfg_map.items():
                if str(k) == sid:
                    cfg = v
                    break
        if cfg is not None:
            enabled = getattr(cfg, "enabled", None)
            if enabled is None:
                return None, "scanner_enabled_unknown"
            return bool(enabled), None

        # Disabled scanners are often dropped from configs; `scanners` lists project-active guardrails.
        if _scanner_id_in_mapping(sid, ps.scanners):
            return True, None
        if _scanner_id_in_mapping(sid, ps.forcedScanners):
            return True, None

        return False, None
    except Exception as e:
        return None, f"read_failed: {e}"


def _extract_openai_reply(data: dict) -> str:
    """Extract text from OpenAI-compatible response; fallback to compact JSON."""
    if not isinstance(data, dict):
        return "(empty reply)"
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            return content or "(empty reply)"
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, dict):
                    text_val = item.get("text")
                    if isinstance(text_val, str):
                        parts.append(text_val)
            joined = "".join(parts).strip()
            if joined:
                return joined
    return json.dumps(data, ensure_ascii=False)


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
async def api_guardrail_scan(request: Request, payload: GuardrailScanIn):
    """Dedicated endpoint for Guardrail Integration view: only calls F5 Guardrail, returns full guardrail JSON for flow visualization."""
    prompt = (payload.message or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="message is required")
    username = require_user(request)
    raw_settings = get_effective_raw_settings(username)
    settings = get_runtime_settings(raw_settings)
    effective_provider = (payload.provider or "").strip() or (raw_settings.get("default_provider") or "").strip() or DEFAULT_PROVIDER
    send_kwargs = build_send_kwargs(verbose=settings.get("guardrail_verbose", False), provider_override=effective_provider or None)
    reply, guardrail_raw = await call_f5_guardrail(
        prompt, send_kwargs, timeout_seconds=settings["guardrail_timeout_seconds"]
    )
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


@app.post("/api/chat-direct")
async def api_chat_direct(request: Request, payload: DirectChatIn):
    """
    Direct mode: send OpenAI-compatible payload straight to provider URL.
    Bypasses F5 Guardrail. When Enterprise KB Skill (agent_skill_enabled) is ON,
    runs the same ReAct-style tool loop as /api/chat but with the direct LLM.
    """
    username = require_user(request)
    messages = payload.messages if isinstance(payload.messages, list) else []
    if not messages:
        raise HTTPException(status_code=400, detail="messages is required")

    raw_settings = get_effective_raw_settings(username)
    settings = get_runtime_settings(raw_settings)
    if isinstance(payload.agent_skill_enabled, bool):
        settings["agent_skill_enabled"] = payload.agent_skill_enabled

    base_url, api_key, model = _get_direct_provider_config()
    if not base_url or not api_key or not model:
        raise HTTPException(
            status_code=400,
            detail="Direct mode unavailable: missing LLM_PROVIDER_URL / LLM_PROVIDER_KEY_Direct / LLM_PROVIDER_MODEL",
        )

    if settings.get("agent_skill_enabled"):
        user_text = _extract_last_user_text_from_messages(messages)
        if not user_text:
            raise HTTPException(status_code=400, detail="messages must include a user role with content")
        agent_debug_log(settings, "api_chat_direct mode=direct_agent_skill")
        loop_result = await run_agent_skill_loop_direct(
            user_text,
            settings,
            base_url=base_url,
            api_key=api_key,
            model=model,
        )
        return JSONResponse(
            {
                "reply": loop_result["reply"],
                "mode": "direct",
                "direct_agent_skill": True,
                "skill_used": loop_result["skill_used"],
                "agent_trace": loop_result["trace"],
                "agent_tool_calls": loop_result["tool_calls"],
            }
        )

    agent_debug_log(settings, "api_chat_direct mode=direct_plain")
    try:
        reply = await _post_direct_chat_completions(
            messages, base_url=base_url, api_key=api_key, model=model, timeout=60.0
        )
        return JSONResponse({"reply": reply, "mode": "direct", "direct_agent_skill": False})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Direct provider unreachable: {e}")


def _get_provider_options() -> list:
    """从环境变量 PROVIDER_OPTIONS（逗号分隔）读取可选 Provider 列表，供前端下拉使用。每次请求时重新加载项目 .env 以便不重启即可生效。"""
    load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)
    raw = (os.getenv("PROVIDER_OPTIONS") or "").strip()
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def _parse_utc_iso(ts: str) -> Optional[datetime]:
    raw = str(ts or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _percentile(values: List[float], p: float) -> Optional[float]:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    rank = (len(values) - 1) * max(0.0, min(100.0, float(p))) / 100.0
    lo = int(rank)
    hi = min(lo + 1, len(values) - 1)
    frac = rank - lo
    return float(values[lo] * (1.0 - frac) + values[hi] * frac)


def _build_latency_stats(latencies: List[float]) -> dict:
    if not latencies:
        return {
            "count": 0,
            "avg": None,
            "median": None,
            "p90": None,
            "p95": None,
            "min": None,
            "max": None,
        }
    ordered = sorted(float(v) for v in latencies)
    n = len(ordered)
    return {
        "count": n,
        "avg": round(sum(ordered) / n, 2),
        "median": round(_percentile(ordered, 50) or 0.0, 2),
        "p90": round(_percentile(ordered, 90) or 0.0, 2),
        "p95": round(_percentile(ordered, 95) or 0.0, 2),
        "min": round(ordered[0], 2),
        "max": round(ordered[-1], 2),
    }


def _empty_user_activity_payload(selected_range: str, start_iso: Optional[str], end_iso: Optional[str]) -> dict:
    return {
        "range": selected_range,
        "start": start_iso,
        "end": end_iso,
        "total_records": 0,
        "invalid_lines": 0,
        "negative_latency_records": 0,
        "activity_by_user": [],
        "latency_seconds_stats": _build_latency_stats([]),
        "latency_bucket_histogram": [],
        "daily_activity_trend": [],
        "daily_activity_trend_by_user": [],
        "user_latency_stats": [],
        "hour_of_day_distribution": {"login": [], "threshold_reached": []},
        "weekday_activity_by_user": [],
        "ip_activity_distribution": [],
        "city_activity_distribution": [],
        "slowest_sessions": [],
    }


@app.get("/api/settings")
async def get_settings(request: Request):
    username = require_user(request)
    out = dict(get_effective_raw_settings(username))
    out["provider_options"] = _get_provider_options()
    out["effective_provider"] = (str(out.get("default_provider", "") or "").strip() or (DEFAULT_PROVIDER or "").strip())
    out["username"] = username
    direct_url, direct_key, direct_model = _get_direct_provider_config()
    direct_ready = bool(direct_url and direct_key and direct_model)
    out["direct_available"] = direct_ready
    if not direct_ready:
        out["direct_unavailable_reason"] = "未配置 LLM_PROVIDER_URL / LLM_PROVIDER_KEY_Direct / LLM_PROVIDER_MODEL"
    out["scanner_drift_poll_seconds"] = SCANNER_DRIFT_POLL_SECONDS
    return out

@app.post("/api/settings")
async def post_settings(request: Request, payload: dict = Body(default=None)):
    username = require_user(request)
    clean_payload = dict(payload) if isinstance(payload, dict) else {}
    admin_only_keys = {"kb_dir", "agent_max_steps"}
    if username != "admin":
        forbidden = [k for k in clean_payload.keys() if k in admin_only_keys]
        if forbidden:
            raise HTTPException(status_code=403, detail="only admin can modify kb_dir or agent_max_steps")
    structured = load_structured_settings()
    if username not in structured["user_settings"]:
        structured["user_settings"][username] = _new_user_settings_from_template(structured)

    for k, v in clean_payload.items():
        if k in USER_SCOPED_KEYS:
            structured["user_settings"][username][k] = v
        elif k in GLOBAL_SCOPED_KEYS:
            structured["global_settings"][k] = v

    runtime = get_runtime_settings(
        {
            **structured["global_settings"],
            **structured["user_settings"].get(username, {}),
        }
    )
    for k in USER_SCOPED_KEYS:
        structured["user_settings"][username][k] = runtime[k]
    for k in GLOBAL_SCOPED_KEYS:
        structured["global_settings"][k] = runtime[k]
    save_structured_settings(structured)
    return {"status": "ok", "settings": runtime}


@app.get("/api/prompt-injection-sync-status")
async def get_prompt_injection_sync_status(request: Request):
    """Read-only: SaaS project scanner state for drift detection (SaaS is source of truth for display)."""
    require_user(request)
    if not CALYPSOAI_PROJECT_ID or not PROMPT_INJECTION_SCANNER_ID:
        return {
            "ok": False,
            "error_code": "missing_env",
            "detail": "Set CALYPSOAI_PROJECT_ID and PROMPT_INJECTION_SCANNER_ID in .env",
            "project_id": CALYPSOAI_PROJECT_ID,
            "scanner_id": PROMPT_INJECTION_SCANNER_ID or None,
            "saas_scanner_enabled": None,
            "suggested_local_agent_skill": None,
        }
    enabled, err = _read_prompt_injection_scanner_saas_state()
    suggested = None if enabled is None else (not enabled)
    return {
        "ok": err is None and enabled is not None,
        "error_code": err,
        "detail": None if err is None else str(err),
        "project_id": CALYPSOAI_PROJECT_ID,
        "scanner_id": PROMPT_INJECTION_SCANNER_ID,
        "saas_scanner_enabled": enabled,
        "suggested_local_agent_skill": suggested,
        "version": PROMPT_INJECTION_DEFAULT_VERSION or None,
    }


@app.post("/api/agent-skill-sync")
async def post_agent_skill_sync(request: Request, payload: AgentSkillSyncIn):
    require_user(request)
    sync_result = _sync_prompt_injection_scanner_for_agent_skill(payload.enabled)
    return {"status": "ok", "scanner_sync": sync_result}


@app.get("/api/user-activity")
async def get_user_activity(
    request: Request,
    range_key: str = Query("1m", alias="range"),
    include_admin: bool = Query(True),
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    username = require_user(request)
    if username != "admin":
        raise HTTPException(status_code=403, detail="admin only")

    now_bj = datetime.now(BEIJING_TZ)
    selected_range = str(range_key or "1m").strip().lower()
    start_dt: Optional[datetime] = None
    end_dt: Optional[datetime] = None

    if selected_range == "1m":
        start_dt = (now_bj - timedelta(days=30)).astimezone(timezone.utc)
        end_dt = now_bj.astimezone(timezone.utc)
    elif selected_range == "3m":
        start_dt = (now_bj - timedelta(days=90)).astimezone(timezone.utc)
        end_dt = now_bj.astimezone(timezone.utc)
    elif selected_range == "custom":
        start_dt = _parse_utc_iso(start or "")
        end_dt = _parse_utc_iso(end or "")
        if not start_dt or not end_dt:
            raise HTTPException(status_code=400, detail="custom range requires valid start and end datetime")
        if end_dt < start_dt:
            raise HTTPException(status_code=400, detail="end datetime must be later than start datetime")
    else:
        raise HTTPException(status_code=400, detail="range must be one of: 1m, 3m, custom")

    if not os.path.exists(LOGIN_ACTIVITY_FILE):
        return _empty_user_activity_payload(selected_range, start_dt.isoformat(), end_dt.isoformat())

    filtered_records = []
    invalid_lines = 0
    with open(LOGIN_ACTIVITY_FILE, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except Exception:
                invalid_lines += 1
                continue
            if not isinstance(item, dict):
                invalid_lines += 1
                continue
            login_dt = _parse_utc_iso(str(item.get("login_datetime") or ""))
            if not login_dt:
                invalid_lines += 1
                continue
            if login_dt < start_dt or login_dt > end_dt:
                continue
            uname = str(item.get("username") or "unknown")
            if (not include_admin) and uname.strip().lower() == "admin":
                continue
            threshold_dt = _parse_utc_iso(str(item.get("threshold_reached_datetime") or ""))
            filtered_records.append(
                {
                    "username": uname,
                    "login_dt": login_dt,
                    "threshold_dt": threshold_dt,
                    "session_id": str(item.get("session_id") or ""),
                    "client_ip": str(item.get("client_ip") or "unknown"),
                }
            )

    if not filtered_records:
        payload = _empty_user_activity_payload(selected_range, start_dt.isoformat(), end_dt.isoformat())
        payload["invalid_lines"] = invalid_lines
        return payload

    user_counts: Dict[str, int] = defaultdict(int)
    user_latencies: Dict[str, List[float]] = defaultdict(list)
    day_counts: Dict[str, int] = defaultdict(int)
    day_counts_by_user: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    weekday_by_user: Dict[str, List[int]] = defaultdict(lambda: [0] * 7)
    hour_login = [0] * 24
    hour_threshold = [0] * 24
    ip_counts: Dict[str, int] = defaultdict(int)
    city_counts: Dict[str, int] = defaultdict(int)
    latency_values: List[float] = []
    negative_latency_records = 0
    slowest_sessions: List[dict] = []

    for rec in filtered_records:
        uname = rec["username"] or "unknown"
        login_local = rec["login_dt"].astimezone(BEIJING_TZ)
        user_counts[uname] += 1
        client_ip = rec["client_ip"] or "unknown"
        ip_counts[client_ip] += 1
        city_counts[_resolve_city_by_ip(client_ip)] += 1
        day_key = login_local.strftime("%Y-%m-%d")
        day_counts[day_key] += 1
        day_counts_by_user[uname][day_key] += 1
        weekday_by_user[uname][login_local.weekday()] += 1
        hour_login[login_local.hour] += 1

        threshold_dt = rec["threshold_dt"]
        if threshold_dt:
            threshold_local = threshold_dt.astimezone(BEIJING_TZ)
            hour_threshold[threshold_local.hour] += 1
            latency_sec = (threshold_dt - rec["login_dt"]).total_seconds()
            if latency_sec < 0:
                negative_latency_records += 1
            else:
                latency_values.append(latency_sec)
                user_latencies[uname].append(latency_sec)
                slowest_sessions.append(
                    {
                        "username": uname,
                        "session_id": rec["session_id"],
                        "client_ip": rec["client_ip"],
                        "login_datetime": login_local.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
                        "threshold_reached_datetime": threshold_local.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
                        "latency_seconds": round(latency_sec, 2),
                    }
                )

    activity_by_user = [
        {"username": k, "count": v}
        for k, v in sorted(user_counts.items(), key=lambda x: (-x[1], x[0].lower()))
    ]
    daily_activity_trend = [
        {"date": d, "count": c}
        for d, c in sorted(day_counts.items(), key=lambda x: x[0])
    ]
    daily_activity_trend_by_user = []
    for uname, per_day in sorted(day_counts_by_user.items(), key=lambda x: x[0].lower()):
        series = [{"date": d, "count": c} for d, c in sorted(per_day.items(), key=lambda x: x[0])]
        daily_activity_trend_by_user.append({"username": uname, "series": series})
    user_latency_stats = []
    for uname, vals in sorted(user_latencies.items(), key=lambda x: x[0].lower()):
        s = _build_latency_stats(vals)
        user_latency_stats.append(
            {
                "username": uname,
                "count": s["count"],
                "avg": s["avg"],
                "median": s["median"],
                "p90": s["p90"],
            }
        )

    latency_bucket_defs = [
        ("0-10s", 0, 10),
        ("10-30s", 10, 30),
        ("30-60s", 30, 60),
        ("1-3m", 60, 180),
        ("3-10m", 180, 600),
        ("10m+", 600, None),
    ]
    latency_bucket_histogram = []
    for label, lo, hi in latency_bucket_defs:
        if hi is None:
            count = sum(1 for v in latency_values if v >= lo)
        else:
            count = sum(1 for v in latency_values if v >= lo and v < hi)
        latency_bucket_histogram.append({"bucket": label, "count": count})

    login_hour_dist = [{"hour": h, "count": c} for h, c in enumerate(hour_login)]
    threshold_hour_dist = [{"hour": h, "count": c} for h, c in enumerate(hour_threshold)]
    ip_activity_distribution = [
        {"client_ip": ip, "count": c}
        for ip, c in sorted(ip_counts.items(), key=lambda x: (-x[1], x[0]))
    ]
    city_activity_distribution = [
        {"city": city, "count": c}
        for city, c in sorted(city_counts.items(), key=lambda x: (-x[1], x[0]))
    ]
    weekday_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    weekday_activity_by_user = []
    for uname, counts in sorted(weekday_by_user.items(), key=lambda x: x[0].lower()):
        total = sum(counts)
        favorite_idx = max(range(7), key=lambda i: counts[i]) if total > 0 else None
        weekday_activity_by_user.append(
            {
                "username": uname,
                "counts": [{"weekday": weekday_labels[i], "count": int(counts[i])} for i in range(7)],
                "favorite_weekday": (weekday_labels[favorite_idx] if favorite_idx is not None else None),
                "total": total,
            }
        )
    slowest_sessions = sorted(slowest_sessions, key=lambda x: -x["latency_seconds"])[:10]

    return {
        "timezone": "Asia/Shanghai",
        "range": selected_range,
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat(),
        "total_records": len(filtered_records),
        "invalid_lines": invalid_lines,
        "negative_latency_records": negative_latency_records,
        "activity_by_user": activity_by_user,
        "latency_seconds_stats": _build_latency_stats(latency_values),
        "latency_bucket_histogram": latency_bucket_histogram,
        "daily_activity_trend": daily_activity_trend,
        "daily_activity_trend_by_user": daily_activity_trend_by_user,
        "user_latency_stats": user_latency_stats,
        "hour_of_day_distribution": {
            "login": login_hour_dist,
            "threshold_reached": threshold_hour_dist,
        },
        "weekday_activity_by_user": weekday_activity_by_user,
        "ip_activity_distribution": ip_activity_distribution,
        "city_activity_distribution": city_activity_distribution,
        "slowest_sessions": slowest_sessions,
    }
