"""Simulated MCP client/server runtime for agentic tools."""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable, Dict, List

from .tools import tools_catalog

ToolDispatch = Callable[[str, Dict[str, Any], str, str], Dict[str, Any]]


def _schema_type_from_token(token: str) -> str:
    t = (token or "").strip().lower()
    if t in ("int", "integer"):
        return "integer"
    if t in ("number", "float", "double"):
        return "number"
    if t in ("bool", "boolean"):
        return "boolean"
    if t in ("array", "list"):
        return "array"
    if t in ("object", "dict", "map"):
        return "object"
    return "string"


def build_openai_tools(agent_name: str) -> List[dict]:
    out: List[dict] = []
    for item in tools_catalog(agent_name):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        raw_schema = item.get("args_schema") if isinstance(item.get("args_schema"), dict) else {}
        properties: Dict[str, Any] = {}
        required: List[str] = []
        for k, v in raw_schema.items():
            arg_name = str(k or "").strip()
            if not arg_name:
                continue
            properties[arg_name] = {"type": _schema_type_from_token(str(v))}
            required.append(arg_name)
        out.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": str(item.get("description") or ""),
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            }
        )
    return out


class MockMcpServer:
    """In-process MCP-style server that exposes the existing tool dispatcher."""

    def __init__(self, tool_dispatch: ToolDispatch):
        self._tool_dispatch = tool_dispatch

    def list_tools(self, agent_name: str) -> List[dict]:
        return build_openai_tools(agent_name)

    def call_tool(
        self,
        *,
        agent_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
        scenario: str,
        user_prompt: str,
        tool_call_id: str,
    ) -> Dict[str, Any]:
        safe_args = arguments if isinstance(arguments, dict) else {}
        result = self._tool_dispatch(tool_name, safe_args, scenario, user_prompt)
        mcp_request_id = f"mcp_{uuid.uuid4().hex[:12]}"
        return {
            "tool_call_id": tool_call_id,
            "mcp_request_id": mcp_request_id,
            "tool_name": tool_name,
            "agent_name": agent_name,
            "result": result if isinstance(result, dict) else {"raw": str(result)},
        }


class MockMcpClient:
    """In-process MCP-style client used by LangGraph nodes."""

    def __init__(self, server: MockMcpServer):
        self._server = server

    def list_tools(self, agent_name: str) -> List[dict]:
        return self._server.list_tools(agent_name)

    def call_tool(
        self,
        *,
        agent_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
        scenario: str,
        user_prompt: str,
        tool_call_id: str,
    ) -> Dict[str, Any]:
        return self._server.call_tool(
            agent_name=agent_name,
            tool_name=tool_name,
            arguments=arguments,
            scenario=scenario,
            user_prompt=user_prompt,
            tool_call_id=tool_call_id,
        )

    @staticmethod
    def to_tool_message_content(tool_envelope: Dict[str, Any]) -> str:
        payload = tool_envelope.get("result") if isinstance(tool_envelope, dict) else {}
        text = json.dumps(payload if isinstance(payload, dict) else {"raw": str(payload)}, ensure_ascii=False)
        return json.dumps([{"type": "text", "text": text}], ensure_ascii=False)
