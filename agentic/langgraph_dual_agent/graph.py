"""LangGraph runtime for dual-agent workflow."""

import json
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, TypedDict

from langgraph.graph import END, StateGraph

from .mcp_runtime import MockMcpClient, MockMcpServer
from .tools import get_tool_config, tools_catalog

LlmCall = Callable[[str, List[dict]], Awaitable[Tuple[str, str]]]
LlmToolCall = Callable[
    [str, List[dict], List[dict], Dict[str, Any]],
    Awaitable[Tuple[dict, str]],
]
ToolDispatch = Callable[[str, Dict[str, Any], str, str], Dict[str, Any]]
TraceLogger = Callable[[str, dict], None]


class AgentState(TypedDict):
    prompt: str
    scenario: str
    session_id: str
    now_ts: int
    trace: List[dict]
    step_index: int
    blocked: bool
    risk_detected: bool
    final_reply: str
    research_objective: str
    action_objective: str
    research_observations: List[str]
    action_observations: List[str]
    research_round: int
    action_round: int
    research_done: bool
    action_done: bool
    research_tool_used: bool
    action_tool_used: bool
    research_tools_done: List[str]
    action_tools_done: List[str]
    research_messages: List[dict]
    action_messages: List[dict]
    agentic_tool_protocol: str


def _parse_json_event(text: str) -> Tuple[Optional[dict], Optional[str]]:
    raw = (text or "").strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None, "no json object found"
    body = raw[start : end + 1]
    try:
        obj = json.loads(body)
    except Exception as e:
        return None, f"json parse failed: {e}"
    if not isinstance(obj, dict):
        return None, "json object must be dict"
    return obj, None


def _legal_trim_text(text: str, max_len: int = 50) -> str:
    s = (text or "").strip().replace("\n", " ")
    if len(s) <= max_len:
        return s
    return s[:max_len]


def _append_trace(state: AgentState, logger: TraceLogger, item: dict) -> AgentState:
    step_index = int(state.get("step_index", 0)) + 1
    row = {"step_index": step_index, "session_id": state["session_id"], "ts": int(state["now_ts"]) + step_index - 1, **item}
    trace = list(state.get("trace", []))
    trace.append(row)
    logger(state["session_id"], row)
    return {**state, "step_index": step_index, "trace": trace}


def _parse_tool_call_arguments(raw_args: Any) -> Dict[str, Any]:
    if isinstance(raw_args, dict):
        return raw_args
    if isinstance(raw_args, str):
        try:
            obj = json.loads(raw_args)
            if isinstance(obj, dict):
                return obj
        except Exception:
            return {}
    return {}


def build_langgraph_runner(
    llm_call: LlmCall,
    tool_dispatch: ToolDispatch,
    trace_logger: TraceLogger,
    *,
    llm_tool_call: Optional[LlmToolCall] = None,
    tool_protocol: str = "legacy_json_prompt",
):
    mcp_client = MockMcpClient(MockMcpServer(tool_dispatch))

    def build_default_tool_args(tool_name: str, state: AgentState) -> Dict[str, Any]:
        if tool_name == "get_vendor_profile":
            return {"vendor_id": "vendor-001"}
        if tool_name == "get_price_history":
            return {"item_id": "item-llm-gateway", "vendor_id": "vendor-001"}
        if tool_name == "search_policy_docs":
            return {"query": state["prompt"], "top_k": 3}
        if tool_name == "create_risk_report":
            return {"summary": "Generate structured procurement risk report based on gathered evidence."}
        if tool_name == "submit_approval_request":
            return {
                "vendor_id": "vendor-001",
                "amount_usd": 138000,
                "approvers": ["procurement-manager", "security-officer"],
            }
        if tool_name == "notify_procurement":
            return {"channel": "slack://procurement-room", "message": "Approval ticket created and pending review."}
        if tool_name == "send_email":
            return {
                "to_email": "user@example.com",
                "subject": "Procurement workflow update",
                "content": "The requested agentic workflow has been processed. Please review the attached summary.",
            }
        return {}

    async def supervisor_plan(state: AgentState) -> AgentState:
        messages = [
            {"role": "system", "content": "You are SupervisorAgent. Return strict JSON only. Format: {\"type\":\"final\",\"research_objective\":\"...\",\"action_objective\":\"...\"}"},
            {"role": "user", "content": f"Scenario={state['scenario']}\nUser task={state['prompt']}\nGenerate concise objectives."},
        ]
        text, finish = await llm_call(state["session_id"], messages)
        obj, err = _parse_json_event(text)
        research_objective = f"Analyze risks for task: {state['prompt']}"
        action_objective = f"Execute procurement workflow for task: {state['prompt']}"
        if isinstance(obj, dict):
            research_objective = str(obj.get("research_objective") or research_objective)
            action_objective = str(obj.get("action_objective") or action_objective)
        return _append_trace(
            {**state, "research_objective": research_objective, "action_objective": action_objective},
            trace_logger,
            {
                "agent_name": "SupervisorAgent",
                "action_type": "plan",
                "summary": (text if not err else f"parse_error: {err}; raw={text[:280]}")[:500],
                "outcome": finish,
                "guardrail_outcome": "cleared",
                "route_decision": "to_research: objectives_ready",
            },
        )

    async def research_node(state: AgentState) -> AgentState:
        next_state = {**state, "research_round": int(state.get("research_round", 0)) + 1}
        protocol = str(state.get("agentic_tool_protocol") or tool_protocol or "legacy_json_prompt").strip().lower()
        if protocol == "openai_tool_calls_mcp_sim" and llm_tool_call is not None:
            messages = list(state.get("research_messages") or [])
            if not messages:
                messages = [
                    {
                        "role": "system",
                        "content": (
                            "You are ResearchAgent. Use available tools when needed. "
                            "When enough information is gathered, answer concisely."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Objective: {state['research_objective']}\n"
                            f"User task: {state['prompt']}\n"
                            "Collect evidence using tools before concluding."
                        ),
                    },
                ]
            tools = mcp_client.list_tools("ResearchAgent")
            assistant_msg, finish = await llm_tool_call(
                state["session_id"],
                messages,
                tools,
                {"tool_choice": "auto", "thinking": {"type": "disabled"}},
            )
            msg = assistant_msg if isinstance(assistant_msg, dict) else {}
            messages.append(msg)
            tool_calls = msg.get("tool_calls") if isinstance(msg.get("tool_calls"), list) else []
            if tool_calls:
                obs = list(next_state.get("research_observations", []))
                tool_names: List[str] = []
                risk_tags: List[str] = []
                tool_call_ids: List[str] = []
                mcp_request_ids: List[str] = []
                tool_args_list: List[Dict[str, Any]] = []
                tool_results_list: List[Dict[str, Any]] = []
                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        continue
                    tc_id = str(tc.get("id") or "").strip() or "call_missing_id"
                    fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
                    tool_name = str(fn.get("name") or "").strip()
                    if not tool_name:
                        continue
                    tool_args = _parse_tool_call_arguments(fn.get("arguments"))
                    env = mcp_client.call_tool(
                        agent_name="ResearchAgent",
                        tool_name=tool_name,
                        arguments=tool_args,
                        scenario=state["scenario"],
                        user_prompt=state["prompt"],
                        tool_call_id=tc_id,
                    )
                    tool_result = env.get("result") if isinstance(env.get("result"), dict) else {}
                    mcp_request_id = str(env.get("mcp_request_id") or "").strip()
                    messages.append(
                        {
                            "role": "tool",
                            "name": tool_name,
                            "tool_call_id": tc_id,
                            "content": mcp_client.to_tool_message_content(env),
                        }
                    )
                    obs.append(json.dumps(tool_result, ensure_ascii=False)[:500])
                    tool_names.append(tool_name)
                    tool_call_ids.append(tc_id)
                    if mcp_request_id:
                        mcp_request_ids.append(mcp_request_id)
                    tool_args_list.append(tool_args)
                    tool_results_list.append(tool_result)
                    if isinstance(tool_result.get("risk_tags"), list):
                        risk_tags.extend([str(x) for x in tool_result["risk_tags"] if str(x).strip()])
                next_state["research_messages"] = messages
                next_state["research_observations"] = obs
                next_state["research_tool_used"] = True
                next_state["risk_detected"] = bool(next_state.get("risk_detected")) or bool(risk_tags)
                return _append_trace(
                    next_state,
                    trace_logger,
                    {
                        "agent_name": "ResearchAgent",
                        "action_type": "tool_call",
                        "tool_name": tool_names[0] if tool_names else "",
                        "tool_args": tool_args_list[0] if tool_args_list else {},
                        "tool_result": tool_results_list[0] if tool_results_list else {},
                        "tool_call_id": tool_call_ids[0] if tool_call_ids else "",
                        "tool_call_ids": tool_call_ids,
                        "mcp_request_id": mcp_request_ids[0] if mcp_request_ids else "",
                        "mcp_request_ids": mcp_request_ids,
                        "tool_args_list": tool_args_list,
                        "tool_results_list": tool_results_list,
                        "summary": ("mcp_sim tool_calls: " + ", ".join(tool_names))[:500],
                        "outcome": finish,
                        "guardrail_outcome": "cleared",
                        "risk_tags": risk_tags,
                        "route_decision": "stay_on_research: openai_tool_calls",
                    },
                )
            answer = str(msg.get("content") or "(empty analysis)")
            next_state["research_messages"] = messages
            next_state["research_done"] = True
            return _append_trace(
                next_state,
                trace_logger,
                {
                    "agent_name": "ResearchAgent",
                    "action_type": "final",
                    "summary": answer[:500],
                    "outcome": finish,
                    "guardrail_outcome": "cleared",
                    "route_decision": "to_action: research_final_ready",
                },
            )
        tools = tools_catalog("ResearchAgent")
        prompt = (
            "You are ResearchAgent. Decide which tool is needed next, or finish.\n"
            "Return STRICT JSON only.\n"
            f"Tools:\n{json.dumps(tools, ensure_ascii=False)}\n"
            "Tool format: {\"type\":\"tool_call\",\"name\":\"...\",\"arguments\":{...}}\n"
            "Final format: {\"type\":\"final\",\"answer\":\"...\"}\n\n"
            f"Objective: {state['research_objective']}\n"
            f"Observations: {' | '.join(state['research_observations']) if state['research_observations'] else '(none)'}"
        )
        text, finish = await llm_call(state["session_id"], [{"role": "user", "content": prompt}])
        obj, err = _parse_json_event(text)
        if err or not isinstance(obj, dict):
            # graceful fallback: one useful tool call instead of forcing all tools
            tool_name = "get_vendor_profile"
            tool_args = build_default_tool_args(tool_name, state)
            tool_result = tool_dispatch(tool_name, tool_args, state["scenario"], state["prompt"])
            obs = list(next_state.get("research_observations", []))
            obs.append(json.dumps(tool_result, ensure_ascii=False)[:500])
            next_state["research_observations"] = obs
            next_state["research_tool_used"] = True
            next_state["risk_detected"] = bool(next_state.get("risk_detected")) or bool(tool_result.get("risk_tags") or [])
            return _append_trace(
                next_state,
                trace_logger,
                {
                    "agent_name": "ResearchAgent",
                    "action_type": "tool_call",
                    "tool_name": tool_name,
                    "tool_call_id": f"legacy_research_fallback_{next_state['research_round']}",
                    "mcp_request_id": "legacy_local_dispatch",
                    "tool_args": tool_args,
                    "tool_result": tool_result,
                    "summary": f"{tool_name}: fallback_tool_call_after_parse_error"[:500],
                    "outcome": finish,
                    "guardrail_outcome": "cleared",
                    "risk_tags": tool_result.get("risk_tags") or [],
                    "route_decision": "stay_on_research: fallback_tool_call",
                },
            )

        event_type = str(obj.get("type") or "").lower()
        if event_type == "tool_call":
            tool_name = str(obj.get("name") or "").strip()
            tool_args = obj.get("arguments") if isinstance(obj.get("arguments"), dict) else {}
            if tool_name not in [x["name"] for x in tools]:
                tool_name = "search_policy_docs"
                tool_args = build_default_tool_args(tool_name, state)
            elif not tool_args:
                tool_args = build_default_tool_args(tool_name, state)
            tool_result = tool_dispatch(tool_name, tool_args, state["scenario"], state["prompt"])
            obs = list(next_state.get("research_observations", []))
            obs.append(json.dumps(tool_result, ensure_ascii=False)[:500])
            next_state["research_observations"] = obs
            next_state["research_tool_used"] = True
            next_state["risk_detected"] = bool(next_state.get("risk_detected")) or bool(tool_result.get("risk_tags") or [])
            return _append_trace(
                next_state,
                trace_logger,
                {
                    "agent_name": "ResearchAgent",
                    "action_type": "tool_call",
                    "tool_name": tool_name,
                    "tool_call_id": f"legacy_research_model_{next_state['research_round']}",
                    "mcp_request_id": "legacy_local_dispatch",
                    "tool_args": tool_args,
                    "tool_result": tool_result,
                    "summary": (
                        (f"{tool_name}: " + str(tool_result.get("detail") or "ok"))[:500]
                    ),
                    "outcome": finish,
                    "guardrail_outcome": "cleared",
                    "risk_tags": tool_result.get("risk_tags") or [],
                    "route_decision": "stay_on_research: model_selected_tool",
                },
            )

        answer = str(obj.get("answer") or "(empty analysis)")
        next_state["research_done"] = True
        return _append_trace(
            next_state,
            trace_logger,
            {
                "agent_name": "ResearchAgent",
                "action_type": "final",
                "summary": answer[:500],
                "outcome": finish,
                "guardrail_outcome": "cleared",
                "route_decision": "to_action: research_final_ready",
            },
        )

    async def action_node(state: AgentState) -> AgentState:
        next_state = {**state, "action_round": int(state.get("action_round", 0)) + 1}
        protocol = str(state.get("agentic_tool_protocol") or tool_protocol or "legacy_json_prompt").strip().lower()
        if protocol == "openai_tool_calls_mcp_sim" and llm_tool_call is not None:
            messages = list(state.get("action_messages") or [])
            if not messages:
                messages = [
                    {
                        "role": "system",
                        "content": (
                            "You are ActionAgent. Use tools to execute tasks. "
                            "When complete, return a concise final response."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Objective: {state['action_objective']}\n"
                            f"User task: {state['prompt']}\n"
                            f"Research context: {' | '.join(state['research_observations']) if state['research_observations'] else '(none)'}"
                        ),
                    },
                ]
            tools = mcp_client.list_tools("ActionAgent")
            assistant_msg, finish = await llm_tool_call(
                state["session_id"],
                messages,
                tools,
                {"tool_choice": "auto", "thinking": {"type": "disabled"}},
            )
            msg = assistant_msg if isinstance(assistant_msg, dict) else {}
            messages.append(msg)
            tool_calls = msg.get("tool_calls") if isinstance(msg.get("tool_calls"), list) else []
            if tool_calls:
                obs = list(next_state.get("action_observations", []))
                tool_names: List[str] = []
                risk_tags: List[str] = []
                tool_call_ids: List[str] = []
                mcp_request_ids: List[str] = []
                tool_args_list: List[Dict[str, Any]] = []
                tool_results_list: List[Dict[str, Any]] = []
                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        continue
                    tc_id = str(tc.get("id") or "").strip() or "call_missing_id"
                    fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
                    tool_name = str(fn.get("name") or "").strip()
                    if not tool_name:
                        continue
                    tool_args = _parse_tool_call_arguments(fn.get("arguments"))
                    env = mcp_client.call_tool(
                        agent_name="ActionAgent",
                        tool_name=tool_name,
                        arguments=tool_args,
                        scenario=state["scenario"],
                        user_prompt=state["prompt"],
                        tool_call_id=tc_id,
                    )
                    tool_result = env.get("result") if isinstance(env.get("result"), dict) else {}
                    mcp_request_id = str(env.get("mcp_request_id") or "").strip()
                    messages.append(
                        {
                            "role": "tool",
                            "name": tool_name,
                            "tool_call_id": tc_id,
                            "content": mcp_client.to_tool_message_content(env),
                        }
                    )
                    obs.append(json.dumps(tool_result, ensure_ascii=False)[:500])
                    tool_names.append(tool_name)
                    tool_call_ids.append(tc_id)
                    if mcp_request_id:
                        mcp_request_ids.append(mcp_request_id)
                    tool_args_list.append(tool_args)
                    tool_results_list.append(tool_result)
                    if isinstance(tool_result.get("risk_tags"), list):
                        risk_tags.extend([str(x) for x in tool_result["risk_tags"] if str(x).strip()])
                next_state["action_messages"] = messages
                next_state["action_observations"] = obs
                next_state["action_tool_used"] = True
                next_state["risk_detected"] = bool(next_state.get("risk_detected")) or bool(risk_tags)
                return _append_trace(
                    next_state,
                    trace_logger,
                    {
                        "agent_name": "ActionAgent",
                        "action_type": "tool_call",
                        "tool_name": tool_names[0] if tool_names else "",
                        "tool_args": tool_args_list[0] if tool_args_list else {},
                        "tool_result": tool_results_list[0] if tool_results_list else {},
                        "tool_call_id": tool_call_ids[0] if tool_call_ids else "",
                        "tool_call_ids": tool_call_ids,
                        "mcp_request_id": mcp_request_ids[0] if mcp_request_ids else "",
                        "mcp_request_ids": mcp_request_ids,
                        "tool_args_list": tool_args_list,
                        "tool_results_list": tool_results_list,
                        "summary": ("mcp_sim tool_calls: " + ", ".join(tool_names))[:500],
                        "outcome": finish,
                        "guardrail_outcome": "cleared",
                        "risk_tags": risk_tags,
                        "route_decision": "stay_on_action: openai_tool_calls",
                    },
                )
            answer = str(msg.get("content") or "(empty action)")
            next_state["action_messages"] = messages
            next_state["action_done"] = True
            next_state["risk_detected"] = bool(next_state.get("risk_detected")) or answer.upper().startswith("BLOCK")
            return _append_trace(
                next_state,
                trace_logger,
                {
                    "agent_name": "ActionAgent",
                    "action_type": "final",
                    "summary": answer[:500],
                    "outcome": finish,
                    "guardrail_outcome": "cleared",
                    "risk_tags": ["model_self_reported_risk"] if answer.upper().startswith("BLOCK") else [],
                    "route_decision": "to_finalize: action_final_ready",
                },
            )
        tools = tools_catalog("ActionAgent")
        prompt = (
            "You are ActionAgent. Decide next tool by user intent, or finish.\n"
            "Return STRICT JSON only.\n"
            f"Tools:\n{json.dumps(tools, ensure_ascii=False)}\n"
            "Tool format: {\"type\":\"tool_call\",\"name\":\"...\",\"arguments\":{...}}\n"
            "Final format: {\"type\":\"final\",\"answer\":\"...\"}\n\n"
            "If the user asks to email results, call send_email. You may omit subject/content and let tool auto-compose.\n"
            f"Objective: {state['action_objective']}\n"
            f"Research context: {' | '.join(state['research_observations']) if state['research_observations'] else '(none)'}\n"
            f"Observations: {' | '.join(state['action_observations']) if state['action_observations'] else '(none)'}"
        )
        text, finish = await llm_call(state["session_id"], [{"role": "user", "content": prompt}])
        obj, err = _parse_json_event(text)
        if err or not isinstance(obj, dict):
            tool_name = "create_risk_report"
            tool_args = build_default_tool_args(tool_name, state)
            tool_result = tool_dispatch(tool_name, tool_args, state["scenario"], state["prompt"])
            obs = list(next_state.get("action_observations", []))
            obs.append(json.dumps(tool_result, ensure_ascii=False)[:500])
            next_state["action_observations"] = obs
            next_state["action_tool_used"] = True
            next_state["risk_detected"] = bool(next_state.get("risk_detected")) or bool(tool_result.get("risk_tags") or [])
            return _append_trace(
                next_state,
                trace_logger,
                {
                    "agent_name": "ActionAgent",
                    "action_type": "tool_call",
                    "tool_name": tool_name,
                    "tool_call_id": f"legacy_action_fallback_{next_state['action_round']}",
                    "mcp_request_id": "legacy_local_dispatch",
                    "tool_args": tool_args,
                    "tool_result": tool_result,
                    "summary": f"{tool_name}: fallback_tool_call_after_parse_error"[:500],
                    "outcome": finish,
                    "guardrail_outcome": "cleared",
                    "risk_tags": tool_result.get("risk_tags") or [],
                    "route_decision": "stay_on_action: fallback_tool_call",
                },
            )

        event_type = str(obj.get("type") or "").lower()
        if event_type == "tool_call":
            tool_name = str(obj.get("name") or "").strip()
            tool_args = obj.get("arguments") if isinstance(obj.get("arguments"), dict) else {}
            if tool_name not in [x["name"] for x in tools]:
                tool_name = "create_risk_report"
                tool_args = build_default_tool_args(tool_name, state)
            elif not tool_args:
                tool_args = build_default_tool_args(tool_name, state)
            tool_result = tool_dispatch(tool_name, tool_args, state["scenario"], state["prompt"])
            obs = list(next_state.get("action_observations", []))
            obs.append(json.dumps(tool_result, ensure_ascii=False)[:500])
            next_state["action_observations"] = obs
            next_state["action_tool_used"] = True
            next_state["risk_detected"] = bool(next_state.get("risk_detected")) or bool(tool_result.get("risk_tags") or [])
            return _append_trace(
                next_state,
                trace_logger,
                {
                    "agent_name": "ActionAgent",
                    "action_type": "tool_call",
                    "tool_name": tool_name,
                    "tool_call_id": f"legacy_action_model_{next_state['action_round']}",
                    "mcp_request_id": "legacy_local_dispatch",
                    "tool_args": tool_args,
                    "tool_result": tool_result,
                    "summary": (
                        (f"{tool_name}: " + str(tool_result.get("detail") or "ok"))[:500]
                    ),
                    "outcome": finish,
                    "guardrail_outcome": "cleared",
                    "risk_tags": tool_result.get("risk_tags") or [],
                    "route_decision": "stay_on_action: model_selected_tool",
                },
            )

        answer = str(obj.get("answer") or "(empty action)")
        next_state["action_done"] = True
        next_state["risk_detected"] = bool(next_state.get("risk_detected")) or answer.upper().startswith("BLOCK")
        return _append_trace(
            next_state,
            trace_logger,
            {
                "agent_name": "ActionAgent",
                "action_type": "final",
                "summary": answer[:500],
                "outcome": finish,
                "guardrail_outcome": "cleared",
                "risk_tags": ["model_self_reported_risk"] if answer.upper().startswith("BLOCK") else [],
                "route_decision": "to_finalize: action_final_ready",
            },
        )

    async def supervisor_finalize(state: AgentState) -> AgentState:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are SupervisorAgent. Produce a clear and complete final response for the user. "
                    "Do not include legal analysis here: LegalCounsel will append a separate brief (≤50 Chinese characters) after your output."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Scenario: {state['scenario']}\nTask: {state['prompt']}\n"
                    f"Research observations: {' | '.join(state['research_observations']) if state['research_observations'] else '(none)'}\n"
                    f"Action observations: {' | '.join(state['action_observations']) if state['action_observations'] else '(none)'}\n"
                    f"RiskDetected={state['risk_detected']}"
                ),
            },
        ]
        text, finish = await llm_call(state["session_id"], messages)
        return _append_trace(
            {**state, "final_reply": text[:1200]},
            trace_logger,
            {
                "agent_name": "SupervisorAgent",
                "action_type": "finalize",
                "summary": text[:500],
                "outcome": finish,
                "guardrail_outcome": "cleared",
                "route_decision": "to_legal_counsel: supervisor_final_ready",
            },
        )

    async def legal_counsel_node(state: AgentState) -> AgentState:
        cfg = get_tool_config()
        lc_raw = cfg.get("legal_counsel")
        lc = lc_raw if isinstance(lc_raw, dict) else {}
        topic1 = str(lc.get("followup_topic_1") or "请简要说明与本任务相关的通用合规注意点。").strip()[:800]
        topic2 = str(lc.get("followup_topic_2") or "请简要说明数据对外提供时的风险提示。").strip()[:800]

        report_ctx = str(state.get("final_reply") or "")[:2000]
        legal_messages = [
            {
                "role": "system",
                "content": (
                    "你是法务顾问（Legal Counsel）。只输出不超过50个汉字的一句话法律风险简评。"
                    "禁止工具调用、禁止JSON、不要列表或编号、不要前缀说明。"
                ),
            },
            {
                "role": "user",
                "content": f"以下为业务主流程产出摘要，请仅输出一句中文法律风险简评（总字数≤50）：\n{report_ctx}",
            },
        ]
        legal_text_raw, legal_finish = await llm_call(state["session_id"], legal_messages)
        legal_text = _legal_trim_text(legal_text_raw, 50)

        s1 = _append_trace(
            state,
            trace_logger,
            {
                "agent_name": "LegalCounselAgent",
                "action_type": "legal_review",
                "summary": legal_text,
                "outcome": legal_finish,
                "guardrail_outcome": "cleared",
                "route_decision": "legal_review_done",
            },
        )

        conv1, c1_finish = await llm_call(state["session_id"], [{"role": "user", "content": topic1}])
        s2 = _append_trace(
            s1,
            trace_logger,
            {
                "agent_name": "LegalCounselAgent",
                "action_type": "simple_dialog",
                "dialog_topic_index": 1,
                "summary": (conv1 or "")[:500],
                "outcome": c1_finish,
                "guardrail_outcome": "cleared",
                "route_decision": "followup_dialog_1",
            },
        )

        conv2, c2_finish = await llm_call(state["session_id"], [{"role": "user", "content": topic2}])
        s3 = _append_trace(
            s2,
            trace_logger,
            {
                "agent_name": "LegalCounselAgent",
                "action_type": "simple_dialog",
                "dialog_topic_index": 2,
                "summary": (conv2 or "")[:500],
                "outcome": c2_finish,
                "guardrail_outcome": "cleared",
                "route_decision": "followup_dialog_2",
            },
        )

        base = str(s3.get("final_reply") or "")
        composed = (
            base
            + "\n\n---\n\n## 法务简评（≤50字）\n\n"
            + legal_text
            + "\n\n## 附加话题一\n\n"
            + (conv1 or "").strip()
            + "\n\n## 附加话题二\n\n"
            + (conv2 or "").strip()
        )
        return {**s3, "final_reply": composed[:4500]}

    def route_research(state: AgentState) -> str:
        if state.get("research_done") or int(state.get("research_round", 0)) >= 4:
            return "action"
        return "research"

    def route_action(state: AgentState) -> str:
        if state.get("action_done") or int(state.get("action_round", 0)) >= 4:
            return "finalize"
        return "action"

    graph = StateGraph(AgentState)
    graph.add_node("supervisor_plan", supervisor_plan)
    graph.add_node("research", research_node)
    graph.add_node("action", action_node)
    graph.add_node("finalize", supervisor_finalize)
    graph.add_node("legal_counsel", legal_counsel_node)
    graph.set_entry_point("supervisor_plan")
    graph.add_edge("supervisor_plan", "research")
    graph.add_conditional_edges("research", route_research, {"research": "research", "action": "action"})
    graph.add_conditional_edges("action", route_action, {"action": "action", "finalize": "finalize"})
    graph.add_edge("finalize", "legal_counsel")
    graph.add_edge("legal_counsel", END)
    compiled = graph.compile()

    async def run(prompt: str, scenario: str, session_id: str, now_ts: int) -> dict:
        initial: AgentState = {
            "prompt": prompt,
            "scenario": scenario,
            "session_id": session_id,
            "now_ts": now_ts,
            "trace": [],
            "step_index": 0,
            "blocked": False,
            "risk_detected": False,
            "final_reply": "",
            "research_objective": "",
            "action_objective": "",
            "research_observations": [],
            "action_observations": [],
            "research_round": 0,
            "action_round": 0,
            "research_done": False,
            "action_done": False,
            "research_tool_used": False,
            "action_tool_used": False,
            "research_tools_done": [],
            "action_tools_done": [],
            "research_messages": [],
            "action_messages": [],
            "agentic_tool_protocol": str(tool_protocol or "legacy_json_prompt"),
        }
        out = await compiled.ainvoke(initial)
        return {
            "session_id": out["session_id"],
            "scenario": out["scenario"],
            "blocked": bool(out.get("blocked")),
            "risk_detected": bool(out.get("risk_detected")),
            "reply": str(out.get("final_reply") or ""),
            "trace": list(out.get("trace") or []),
            "runtime_engine": "LangGraph",
        }

    return run
