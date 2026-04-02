"""OpenAI-compatible client for Calypso Agentic runtime."""

from typing import List, Tuple
import json
import httpx


def required_headers(session_id: str, token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "x-cai-metadata-session-id": session_id,
    }


def extract_openai_text(data: dict) -> str:
    if not isinstance(data, dict):
        return "(empty response)"
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        c0 = choices[0] if isinstance(choices[0], dict) else {}
        msg = c0.get("message") if isinstance(c0.get("message"), dict) else {}
        content = msg.get("content")
        if isinstance(content, str):
            return content.strip() or "(empty response)"
    return json.dumps(data, ensure_ascii=False)[:1500]


class CalypsoOpenAIClient:
    def __init__(self, *, base_url: str, token: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.model = model

    async def chat(self, *, session_id: str, messages: List[dict], timeout: float = 60.0) -> Tuple[str, str]:
        url = self.base_url + "/chat/completions"
        body = {"model": self.model, "messages": messages, "stream": False}
        headers = required_headers(session_id, self.token)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, headers=headers, json=body)
        if resp.status_code < 200 or resp.status_code >= 300:
            raise RuntimeError(f"OpenAI-compatible request failed: {(resp.text or '')[:800]}")
        data = resp.json()
        text = extract_openai_text(data)
        finish_reason = ""
        choices = data.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            finish_reason = str(choices[0].get("finish_reason") or "")
        return text, (finish_reason or "stop")
