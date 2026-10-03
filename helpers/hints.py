"""Build guidance text listing preserved subordinate chats for a parent agent."""

from agent import Agent

from usr.plugins.subagent_resume.helpers import links


def _context_line(context) -> str:
    label = getattr(context, "name", None) or "subordinate"
    messages = 0
    try:
        agent = context.agent0
        while agent is not None:
            messages += len(agent.history.all_messages())
            agent = agent.data.get(Agent.DATA_NAME_SUBORDINATE, None)
    except Exception:
        pass
    running = "running" if context.is_running() else "idle"
    return f"- context_id={context.id} name='{label}' [{running}] ({messages} messages preserved)"


def preserved_subordinates_hint(agent: Agent) -> str:
    """One compact hint block for extras; empty when there is nothing to say."""
    try:
        children = links.child_contexts_of(agent.context)
    except Exception:
        return ""
    if not children:
        return ""
    children = sorted(children, key=lambda context: context.created_at)
    lines = [
        "Preserved subordinate chats from before the interruption:",
        *[_context_line(child) for child in children],
        "Continue one with call_subordinate and context_id + reset=false instead of spawning a duplicate.",
    ]
    return "\n".join(lines)
