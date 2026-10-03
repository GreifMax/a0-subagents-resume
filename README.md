# Subagent Resume

**Agent Zero plugin** — fixes the broken parent/subagent resume experience after a stop or restart.

## Purpose

Stopping Agent Zero while an agent is working with a tree of subagents breaks the delegation chain in three ways:

1. **Lost parent links** — the child→parent (`_superior`) link exists only in memory and is dropped on reload, so a resumed subagent that finishes never calls back its parent.
2. **Dangling tool call** — the parent's history ends with an unresolved `call_subordinate` call, so on nudge the model thinks nothing happened and spawns a *duplicate* subagent, ruining the previous work.
3. **Invisible preserved chats** — the stopped subagent chats still exist on disk but the model has no pointer to them.

## Features

- **Restore subordinate links** — rebuilds the in-memory parent↔subordinate links from each child context's persisted `parent_context_id`/`parent_agent_number` output data, whenever a context is about to run again (`AgentContext.communicate` start, with a `monologue_start` safety net). A resumed child that finishes now triggers its parent through the standard `_process_chain` callback.
- **Repair interrupted tool calls** — when a stopped/restarted context's history ends with a dangling tool call, appends a synthetic tool result: "execution was interrupted … preserved subordinate chat context_id=X … continue it with `call_subordinate` + `context_id` + `reset=false`; do NOT spawn a new subordinate." Also keeps histories structurally valid for the Responses API (no orphaned function calls).
- **Continuation hints** — injects a temporary extras block into the parent's prompt listing all preserved subordinate chats (context_id, name, running/idle, message count) so the model continues them instead of starting over.
- **Async wakeup** — `call_subordinate` calls launched inside `parallel` with `wait: false` accept a `wakeup: true` argument. When such a subordinate finishes **and the parent is idle** (it already answered the user), the parent is automatically resumed with a system message telling it to collect the result via the `parallel` tool. If the parent is still working, results stay in the normal `parallel jobs` extras block. A 60s `job_loop` sweeper catches missed wakeups.

Each feature is individually toggleable in settings (Settings → Agent → Subagent Resume).

## Install

1. Copy the `subagent_resume` folder into your Agent Zero `usr/plugins/` directory (local) or install via the community Plugin Index.
2. Restart the WebUI (or use the plugin manager to reload).
3. No dependencies, no external files, no configuration required — works with defaults.

## Usage

Nothing to operate. The next time you stop an instance mid-delegation and reload it:

- Resuming the **bottom** subagent will automatically call back up the chain to the top agent when it finishes.
- Nudging the **top** agent shows it the preserved subagent chat(s) and instructs it to continue them instead of creating duplicates.

## Troubleshooting

- **Plugin seems inactive** — check Settings → Agent → Subagent Resume → *Enabled*, and that the chat actually has subordinate contexts (the hint block only appears for parents with children).
- **No synthetic result appended** — repair only runs when the context is *not* running; a live parent legitimately awaits its subordinate's tool result.
- **Duplicate subagent still spawned** — some models ignore the extras hint; the repaired history pointer (context_id in the tool result) is the stronger signal, check that history repair is enabled.

## Screenshots

<!-- TODO before publishing: screenshot of the settings panel next to core settings -->
