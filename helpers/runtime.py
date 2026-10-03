"""Entry points used by the plugin's extensions.

All entry points are idempotent and fail-safe: any internal error is logged
and swallowed so a broken repair can never take down the agent loop.
"""

from agent import Agent, AgentContext

from usr.plugins.subagent_resume.helpers import config, links, repair


def ensure_context_reconciled(context: AgentContext, agent: Agent | None = None) -> None:
    """Reconcile links and repair histories for one context.

    Called when a context is about to run again (communicate start) and as a
    safety net at monologue start. History repair is skipped while the context
    task is alive: a live parent awaiting a subordinate legitimately ends with
    an unresolved tool call.
    """
    if not config.is_enabled(agent or (context.agent0 if context else None)):
        return
    try:
        if config.get_settings(agent).get("restore_links", True):
            # link the context itself (if it is a subordinate of another context)
            # and all of its own subordinate children, so a nudged parent gets
            # its registry rebuilt too - not only a resumed child.
            targets = [context] + list(links.child_contexts_of(context))
            links.reconcile_links(targets)
    except Exception:
        pass
    try:
        running = False
        try:
            running = context.is_running()
        except Exception:
            running = False
        if not running and config.get_settings(agent).get("repair_dangling", True):
            repair.repair_context_history(context)
    except Exception:
        pass


def on_communicate_start(data: dict) -> None:
    """Implicit hook: AgentContext.communicate/start."""
    args = data.get("args") if isinstance(data, dict) else None
    context = args[0] if isinstance(args, tuple) and args else None
    if context is None or not hasattr(context, "agent0"):
        return
    ensure_context_reconciled(context, getattr(context, "streaming_agent", None) or context.agent0)


def on_monologue_start(agent: Agent | None) -> None:
    """Named extension: monologue_start (safety net for any missed path)."""
    if agent is None or not getattr(agent, "context", None):
        return
    ensure_context_reconciled(agent.context, agent)


def on_message_loop_start(agent: Agent | None, loop_data=None) -> None:
    """Named extension: message_loop_start; injects continuation hints.

    The hint is injected as temporary extras (cleared after the turn) so the
    model sees preserved subordinate chats right after a restart/nudge.
    """
    if agent is None or not getattr(agent, "context", None) or loop_data is None:
        return
    if not config.is_enabled(agent):
        return
    if not config.get_settings(agent).get("inject_hints", True):
        return
    try:
        from usr.plugins.subagent_resume.helpers import hints

        hint = hints.preserved_subordinates_hint(agent)
        if hint and agent.number == 0:
            extras = getattr(loop_data, "extras_temporary", None)
            if extras is not None and "subagent_resume" not in extras:
                extras["subagent_resume"] = hint
    except Exception:
        pass
