"""Wakeup: let finished background subordinates call the parent back.

A parallel `call_subordinate` job launched with `wakeup: true` in its tool
args registers here. When the worker's monologue ends, the parent context is
communicated with (only if it is idle - i.e. it already finished answering
the user; otherwise the result stays in the normal extras flow). The wakeup
message tells the parent which subordinate finished so it can collect the
result via the `parallel` tool.

The registry is in-memory by design: it lives exactly as long as the parallel
job store it mirrors (both are per-instance runtime state).
"""

import asyncio
import time

from agent import Agent, AgentContext, UserMessage
from helpers.parallel_tools import (
    PARALLEL_WORKER_JOB_KEY,
    PARALLEL_WORKER_KIND_KEY,
    PARALLEL_WORKER_PARENT_CONTEXT_KEY,
    TERMINAL_STATES,
    _jobs_for_context,
)

_RETRY_INTERVAL_SECONDS = 10.0
_RETRY_DEADLINE_SECONDS = 300.0


class _Registry:
    """Registered wakeup entries: job_id -> info."""

    def __init__(self):
        self._entries: dict[str, dict] = {}

    def register(self, job_id, parent_context_id, worker_context_id, worker_name, tool_name):
        self._entries[job_id] = {
            "job_id": job_id,
            "parent_context_id": parent_context_id,
            "worker_context_id": worker_context_id,
            "worker_name": worker_name,
            "tool_name": tool_name,
            "registered_at": time.time(),
            "woken": False,
        }

    def get(self, job_id):
        return self._entries.get(job_id)

    def pending_for_parent(self, parent_context_id):
        return [
            entry
            for entry in self._entries.values()
            if entry["parent_context_id"] == parent_context_id and not entry["woken"]
        ]

    def mark_woken(self, job_id):
        entry = self._entries.get(job_id)
        if entry:
            entry["woken"] = True

    def sweep_pending(self):
        """All un-woken entries (job_loop safety net)."""
        return [entry for entry in self._entries.values() if not entry["woken"]]


registry = _Registry()


def _wakeup_requested(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def maybe_register_worker(agent) -> None:
    """monologue_start on a worker: register if its job args asked for wakeup."""
    context = getattr(agent, "context", None)
    if not context:
        return
    if context.get_data(PARALLEL_WORKER_KIND_KEY) != "subordinate":
        return
    job_id = str(context.get_data(PARALLEL_WORKER_JOB_KEY) or "")
    parent_context_id = str(context.get_data(PARALLEL_WORKER_PARENT_CONTEXT_KEY) or "")
    if not job_id or not parent_context_id:
        return
    parent_context = AgentContext.get(parent_context_id)
    if not parent_context:
        return
    job = _jobs_for_context(parent_context).get(job_id)
    if not job:
        return
    args = getattr(job, "tool_args", None)
    if not isinstance(args, dict) or not _wakeup_requested(args.get("wakeup")):
        return
    registry.register(
        job_id=job_id,
        parent_context_id=parent_context_id,
        worker_context_id=context.id,
        worker_name=context.name or "subordinate",
        tool_name=getattr(job, "tool_name", "call_subordinate"),
    )


def _wakeup_message(entry) -> UserMessage:
    worker_name = entry.get("worker_name") or "subordinate"
    job_id = entry.get("job_id") or "unknown"
    text = (
        f"A subordinate you launched asynchronously ('{worker_name}', job {job_id}) "
        "has finished. Its result is waiting in the parallel job records. Call the "
        f"`parallel` tool with `action: \"await\"` and `job_ids: [\"{job_id}\"]` to "
        "collect it, then continue your work and report to the user."
    )
    return UserMessage("", system_message=[text])


def _deliver_wakeup(entry) -> bool:
    """Wake the parent for an entry if it is idle and the job finished.

    Returns True when the wakeup was delivered or the entry is finished.
    """
    parent_context = AgentContext.get(entry["parent_context_id"])
    if parent_context is None:
        registry.mark_woken(entry["job_id"])
        return True
    try:
        if parent_context.is_running():
            return False  # still busy: retry later
    except Exception:
        return False
    try:
        registry.mark_woken(entry["job_id"])
        parent_context.communicate(_wakeup_message(entry))
        return True
    except Exception:
        return False


async def _retry_loop(job_id: str) -> None:
    """Retry a deferred wakeup until the parent goes idle or deadline hits."""
    deadline = time.monotonic() + _RETRY_DEADLINE_SECONDS
    while time.monotonic() < deadline:
        await asyncio.sleep(_RETRY_INTERVAL_SECONDS)
        entry = registry.get(job_id)
        if entry is None or entry.get("woken"):
            return
        if _deliver_wakeup(entry):
            return
    registry.mark_woken(job_id)  # give up; extras/sweeper still cover it


_RETRIES: set[str] = set()


def _schedule_retry(job_id: str) -> None:
    if job_id in _RETRIES:
        return
    _RETRIES.add(job_id)
    try:
        task = asyncio.get_event_loop().create_task(_retry_loop(job_id))
        task.add_done_callback(lambda _t, j=job_id: _RETRIES.discard(j))
    except RuntimeError:
        _RETRIES.discard(job_id)


def try_wake_parent(agent) -> bool:
    """monologue_end on a worker: wake the parent if it is idle.

    If the parent is still working, a lightweight retry loop re-checks every
    10s (up to 5 minutes) so the wake happens right after the parent finishes
    answering the user instead of waiting for the 60s sweeper.
    """
    context = getattr(agent, "context", None)
    if not context:
        return False
    job_id = str(context.get_data(PARALLEL_WORKER_JOB_KEY) or "")
    entry = registry.get(job_id) if job_id else None
    if entry is None or entry.get("woken"):
        return False
    if entry.get("worker_context_id") != context.id:
        return False
    delivered = _deliver_wakeup(entry)
    if not delivered:
        _schedule_retry(job_id)
    return True


def pending_hint(agent) -> str:
    """message_loop_start on parent: hint about deferred wakeups."""
    context = getattr(agent, "context", None)
    if not context:
        return ""
    pending = registry.pending_for_parent(context.id)
    if not pending:
        return ""
    lines = [
        "Deferred wakeup notifications (subordinates finished while you were working):"
    ]
    for entry in pending:
        lines.append(
            f"- '{entry['worker_name']}' (job {entry['job_id']}) finished; "
            "collect with `parallel` + `job_ids`."
        )
    return "\n".join(lines)


def sweep() -> int:
    """job_loop safety net: wake idle parents for un-woken registered entries."""
    woken = 0
    for entry in registry.sweep_pending():
        job_id = entry["job_id"]
        parent_context = AgentContext.get(entry["parent_context_id"])
        if parent_context is None:
            registry.mark_woken(job_id)
            continue
        try:
            if parent_context.is_running():
                continue
        except Exception:
            continue
        # only wake for jobs that actually finished
        job = _jobs_for_context(parent_context).get(job_id)
        if job is not None and getattr(job, "state", None) not in TERMINAL_STATES:
            continue
        try:
            registry.mark_woken(job_id)
            parent_context.communicate(_wakeup_message(entry))
            woken += 1
        except Exception:
            continue
    return woken
