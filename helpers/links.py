"""Restore cross-context parent<->subordinate links after a restart.

The framework stores `_superior` / `_subordinates` only in memory (underscore
keys are stripped at serialization). The child context, however, persists
`parent_context_id` / `parent_agent_number` in its output_data. This module
rebuilds the in-memory links from those persisted keys so that
`AgentContext._process_chain` can call the parent back when a resumed
subordinate finishes.
"""

from agent import Agent, AgentContext
from tools.call_subordinate import (
    CHILD_PARENT_AGENT_NUMBER_KEY,
    CHILD_PARENT_CONTEXT_ID_KEY,
    CHILD_SUBORDINATE_SLOT_KEY,
    DEFAULT_SUBORDINATE_SLOT,
    SUBORDINATES_DATA_KEY,
    _register_subordinate,
)


def _agent_by_number(context: AgentContext, number) -> Agent | None:
    """Walk the same-context agent chain (legacy) to find an agent by number."""
    try:
        number = int(number)
    except (TypeError, ValueError):
        return None
    agent = context.agent0
    while agent is not None:
        if agent.number == number:
            return agent
        agent = agent.data.get(Agent.DATA_NAME_SUBORDINATE, None)
    return None


def child_contexts_of(parent_context: AgentContext) -> list[AgentContext]:
    """All live contexts registered (via persisted output_data) under a parent."""
    parent_id = parent_context.id
    return [
        context
        for context in AgentContext.all()
        if context is not parent_context
        and context.get_output_data(CHILD_PARENT_CONTEXT_ID_KEY) == parent_id
    ]


def _link_child(child_context: AgentContext) -> bool:
    parent_id = child_context.get_output_data(CHILD_PARENT_CONTEXT_ID_KEY)
    if not parent_id:
        return False
    parent = AgentContext.get(str(parent_id))
    if parent is None or parent is child_context:
        return False
    parent_agent = _agent_by_number(
        parent, child_context.get_output_data(CHILD_PARENT_AGENT_NUMBER_KEY)
    )
    if parent_agent is None:
        return False
    child_agent = child_context.agent0
    if child_agent is None:
        return False
    if child_agent.data.get(Agent.DATA_NAME_SUPERIOR) is parent_agent:
        return False  # already linked
    slot = (
        child_context.get_output_data(CHILD_SUBORDINATE_SLOT_KEY)
        or DEFAULT_SUBORDINATE_SLOT
    )
    _register_subordinate(parent_agent, child_agent, str(slot))
    return True


def reconcile_links(contexts: list[AgentContext] | None = None) -> int:
    """Rebuild subordinate links for the given contexts (or all live contexts).

    Idempotent: already-linked or orphaned contexts are skipped without error.
    Returns the number of restored links.
    """
    targets = contexts if contexts is not None else AgentContext.all()
    restored = 0
    for context in targets:
        try:
            if _link_child(context):
                restored += 1
        except Exception:
            continue
    return restored


def subordinate_registry(parent: Agent) -> dict:
    registered = parent.get_data(SUBORDINATES_DATA_KEY)
    return registered if isinstance(registered, dict) else {}


def latest_child_context(parent_context: AgentContext) -> AgentContext | None:
    children = child_contexts_of(parent_context)
    if not children:
        return None
    return max(children, key=lambda context: context.created_at)
