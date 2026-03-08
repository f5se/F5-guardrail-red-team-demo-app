"""Skill: read_enterprise_kb

Searches local enterprise knowledge-base files and returns the most relevant
snippets for a given query.  Supports .txt, .md, .json, .csv by default.
"""

import os
import re
from typing import Any, Dict, List

from .base import AbstractSkill
from .utils import BASE_DIR, agent_debug_log, to_int


# ---------------------------------------------------------------------------
# Private helpers – text retrieval utilities
# ---------------------------------------------------------------------------

def _normalize_for_match(text: str) -> str:
    lowered = (text or "").lower()
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", lowered, flags=re.UNICODE)


def _split_keywords(text: str) -> List[str]:
    lowered = (text or "").lower()
    tokens = [t for t in re.findall(r"[\w\-]{2,}", lowered, flags=re.UNICODE) if t]

    cjk_chunks = re.findall(r"[\u4e00-\u9fff]{2,}", lowered)
    for chunk in cjk_chunks:
        for n in (2, 3):
            if len(chunk) < n:
                continue
            for i in range(0, len(chunk) - n + 1):
                tokens.append(chunk[i : i + n])

    unique: List[str] = []
    seen: set = set()
    for t in tokens:
        if t in seen:
            continue
        seen.add(t)
        unique.append(t)
    return unique[:40]


def _score_document(query: str, content: str, keywords: List[str]) -> int:
    q = query.lower().strip()
    c = content.lower()
    q_norm = _normalize_for_match(q)
    c_norm = _normalize_for_match(c)
    score = 0
    if q and q in c:
        score += 5
    if q_norm and q_norm in c_norm:
        score += 5
    for kw in keywords:
        if not kw:
            continue
        if re.search(r"[\u4e00-\u9fff]", kw):
            score += c_norm.count(kw)
        else:
            score += c.count(kw)
    return score


def _extract_snippet(content: str, keywords: List[str], max_chars: int) -> str:
    if not content:
        return ""
    lower = content.lower()
    idx = -1
    for kw in keywords:
        pos = lower.find(kw)
        if pos != -1:
            idx = pos
            break
    if idx == -1:
        return content[:max_chars]
    half = max_chars // 2
    start = max(0, idx - half)
    end = min(len(content), start + max_chars)
    return content[start:end]


def _safe_join_under_base(base_dir: str, target_path: str) -> bool:
    base = os.path.realpath(base_dir)
    target = os.path.realpath(target_path)
    return target == base or target.startswith(base + os.sep)


# ---------------------------------------------------------------------------
# Skill class
# ---------------------------------------------------------------------------

class ReadEnterpriseKBSkill(AbstractSkill):
    name = "read_enterprise_kb"
    description = (
        "Read local enterprise knowledge base files and return relevant snippets"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "top_k": {"type": "integer", "minimum": 1, "maximum": 8},
        },
        "required": ["query"],
    }
    permission = "local_read_kb_only"

    def execute(self, arguments: Dict[str, Any], settings: Dict[str, Any]) -> dict:
        raw_kb_dir = str(settings["kb_dir"])
        kb_dir = raw_kb_dir if os.path.isabs(raw_kb_dir) else os.path.join(BASE_DIR, raw_kb_dir)
        kb_dir = os.path.abspath(kb_dir)
        agent_debug_log(settings, f"tool=read_enterprise_kb start kb_dir={kb_dir}")

        if not os.path.isdir(kb_dir):
            agent_debug_log(settings, "tool=read_enterprise_kb kb_dir_not_found")
            return {"ok": False, "error": f"kb_dir not found: {kb_dir}"}

        query = str(arguments.get("query", "")).strip()
        if not query:
            agent_debug_log(settings, "tool=read_enterprise_kb missing_query")
            return {"ok": False, "error": "query is required"}

        top_k = to_int(arguments.get("top_k", settings["kb_top_k"]), settings["kb_top_k"], 1, 8)
        allowed_ext = settings["kb_allowed_extensions"]
        max_file_chars = settings["kb_max_file_chars"]
        max_result_chars = settings["kb_max_result_chars"]
        keywords = _split_keywords(query)

        ranked = []
        scanned_files = 0
        for root, _, files in os.walk(kb_dir):
            for name in files:
                file_path = os.path.join(root, name)
                if not _safe_join_under_base(kb_dir, file_path):
                    continue
                ext = os.path.splitext(name)[1].lower()
                if ext not in allowed_ext:
                    continue
                scanned_files += 1
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read(max_file_chars)
                except Exception:
                    continue
                if not content.strip():
                    continue
                score = _score_document(query, content, keywords)
                if score <= 0:
                    continue
                ranked.append((score, file_path, content))

        ranked.sort(key=lambda x: x[0], reverse=True)
        hits = []
        total_chars = 0
        for score, path, content in ranked[:top_k]:
            rel_path = os.path.relpath(path, kb_dir)
            snippet = _extract_snippet(content, keywords, 800)
            candidate = len(snippet)
            if total_chars + candidate > max_result_chars:
                remaining = max_result_chars - total_chars
                if remaining <= 0:
                    break
                snippet = snippet[:remaining]
                candidate = len(snippet)
            total_chars += candidate
            hits.append({
                "path": rel_path,
                "score": score,
                "snippet": snippet,
            })

        agent_debug_log(
            settings,
            f"tool=read_enterprise_kb done scanned={scanned_files} ranked={len(ranked)} hits={len(hits)}",
        )
        return {
            "ok": True,
            "kb_dir": kb_dir,
            "scanned_files": scanned_files,
            "hits": hits,
        }
