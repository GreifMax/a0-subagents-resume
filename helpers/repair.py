"""Repair dangling tool calls in a reloaded agent history.

When an instance is stopped while a tool is executing (most importantly
`call_subordinate`), the assistant's tool-call message is persisted without a
matching tool-result message. On the next turn the model sees an unresolved
call, concludes nothing happened, and spawns a duplicate subagent.

This module appends a synthetic tool result for the interrupted call so the
history stays structurally valid (and safe for the Responses API, which
rejects orphaned function calls).
"""

import json

from agent import Agent
from helpers.extract_tools import extract_tool_request
from helpers.llm_result import LLMResult

from usr.plugins.subagent_resume.helpers import links


def _message_tool_calls(message) -> list[dict]:
    """Extract tool call dicts from an AI history message."""
    content = getattr(message, "content", None)
    if not isinstance(content, str) or not content.strip():
        return []
    request = extract_tool_request(content.strip())
    if isinstance(request, dict) and request.get("tool_name"):
        return [request]
    return []


def _is_tool_result_message(message) -> bool:
    """True when a non-AI history message is a tool result (dict content)."""
    if getattr(message, "ai", False):
        return False
    content = getattr(message, "content", None)
    return isinstance(content, dict) and "tool_name" in content and "tool_result" in content


def _trailing_dangling_calls(agent: Agent) -> list[dict]:
    """Tool calls at the very end of history that never received a result.

    A tool result is always appended right after its call (Tool.after_execution),
    so the call is dangling only when the messages after it contain no tool
    result at all. Trailing user/system messages (nudge, interventions) do not
    resolve a call - but they do not make a resolved call dangle again.
    """
    messages = agent.history.all_messages()
    trailing: list = []
    while messages and not messages[-1].ai:
        trailing.append(messages[-1])
        messages = messages[:-1]
    if not messages or not messages[-1].ai:
        return []
    if any(_is_tool_result_message(message) for message in trailing):
        return []  # a result was already appended after the last AI message
    calls = _message_tool_calls(messages[-1])
    return calls if calls else []


def _find_child_context(agent: Agent, tool_args: dict) -> object | None:
    """Locate the preserved subordinate context for an interrupted delegation."""
    context_id = str(tool_args.get("context_id") or tool_args.get("agent_id") or "").strip()
    if context_id:
        from agent import AgentContext

        return AgentContext.get(context_id)
    for context in links.child_contexts_of(agent.context):
        if context.agent0 and context.agent0.data.get(Agent.DATA_NAME_SUPERIOR) is agent:
            return context
    return links.latest_child_context(agent.context)


def _format_interrupted_result(agent: Agent, tool_args: dict, child) -> str:
    parts = [
        "Subordinate execution was interrupted (agent instance was stopped or "
        "restarted). The subordinate's work is preserved."
    ]
    if child is not None:
        parts.append(
            f"Subordinate chat: context_id={child.id}"
            + (f" name='{child.name}'" if getattr(child, "name", None) else "")
            + f" ({len(child.agent0.history.all_messages())} messages preserved)"
        )
        parts.append(
            f"Continue it with call_subordinate using context_id='{child.id}' and "
            "reset=false; do NOT spawn a new subordinate for the same task."
        )
    else:
        parts.append(
            "No preserved subordinate chat was found for this call; verify the task "
            "state before delegating again."
        )
    return " ".join(parts)


def repair_agent_history(agent: Agent) -> int:
    """Append synthetic results for trailing dangling tool calls. Idempotent."""
    repaired = 0
    calls = _trailing_dangling_calls(agent)
    if not calls:
        return 0
    for call in calls:
        tool_name = str(call.get("tool_name") or "")
        tool_args = call.get("tool_args") or {}
        if tool_name == "call_subordinate":
            child = _find_child_context(agent, tool_args)
            if child is not None:
                message = _format_interrupted_result(agent, tool_args, child)
            else:
                message = _format_interrupted_result(agent, tool_args, None)
        else:
            message = (
                f"Tool '{tool_name or 'unknown'}' execution was interrupted "
                "(agent instance was stopped or restarted) and returned no result."
            )
        agent.hist_add_tool_result(tool_name, message)
        repaired += 1
    return repaired


def repair_context_history(context) -> int:
    """Repair all agents in a context's legacy same-context chain."""
    repaired = 0
    agent = context.agent0
    while agent is not None:
        try:
            repaired += repair_agent_history(agent)
        except Exception:
            pass
        agent = agent.data.get(Agent.DATA_NAME_SUBORDINATE, None)
    return repaired


def describe_call(call: dict) -> str:
    try:
        return json.dumps(call, ensure_ascii=False)
    except Exception:
        return str(call)


def _llm_result_sentinel() -> LLMResult:
    return LLMResult.non_llm()