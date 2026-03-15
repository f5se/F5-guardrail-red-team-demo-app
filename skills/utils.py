"""Shared utility functions used by skills and main application."""

import os
from datetime import datetime, timezone
from typing import Any, List, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def to_int(
    v: Any,
    default: int,
    min_value: Optional[int] = None,
    max_value: Optional[int] = None,
) -> int:
    try:
        value = int(v)
    except Exception:
        value = default
    if min_value is not None:
        value = max(min_value, value)
    if max_value is not None:
        value = min(max_value, value)
    return value


def to_float(
    v: Any,
    default: float,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
) -> float:
    try:
        value = float(v)
    except Exception:
        value = default
    if min_value is not None:
        value = max(min_value, value)
    if max_value is not None:
        value = min(max_value, value)
    return value


def to_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in {"1", "true", "yes", "on"}
    return bool(v)


def normalize_extensions(raw: Any) -> List[str]:
    if isinstance(raw, list):
        parts = [str(x).strip().lower() for x in raw]
    else:
        parts = [x.strip().lower() for x in str(raw or "").split(",")]
    clean = []
    for p in parts:
        if not p:
            continue
        if not p.startswith("."):
            p = "." + p
        clean.append(p)
    return clean or [".txt", ".md", ".json", ".csv"]


def agent_debug_log(settings: dict, message: str):
    if settings.get("agent_debug_enabled"):
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        print(f"[AGENT-DEBUG] {ts} {message}")
