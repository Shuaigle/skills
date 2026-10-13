---
name: jev
description: Jev routing for task models, skills, and subagent models. Use to configure routing, begin a task with enabled decisions, or choose a model before spawning a subagent.
---

# Jev

Let Jev choose a task model, an optional skill, or a subagent model from live candidates. Enable each decision independently; the host applies the choice.

In Claude Code with this plugin's native mod loaded, read [native routing](references/claude-native.md). Its `/jev` commands own the flags; it applies task and subagent models automatically to the same conversation's requests. Follow the emitted native context and route only optional skills here, without repeating model decisions or waiting for manual model switches. Other hosts retain the workflow below.

## Control

Keep an `enabled_decisions` set, routing preferences, and pending choices in this conversation. Valid decisions are `task`, `skill`, and `subagent`. A new conversation starts with all three **off**. Runtime routing writes no global settings, hooks, or state files.

| Request | Action | Done when |
|---|---|---|
| `jev on [decisions]` | Add the named decisions; bare `on` adds only `task`. Expand `all` to all three. Check `JEV_API_KEY` presence without displaying it; a missing key or unknown decision leaves the set unchanged. | Report all three flags and conversation scope. Route an accompanying task next. |
| `jev off [decisions]` | Remove the named decisions; bare `off` or `off all` clears the set. Clear pending choices for disabled decisions; keep the current model. | Report all three flags. Disabled decisions make no Jev requests. |
| `jev status`, or `jev` alone | Report all three flags and pending choices. | Make no API request. |

For example, `jev on skill subagent` enables those two without changing `task`; `jev off task` disables only task-model routing. An explicit request to use **only** named decisions replaces the set. Configuration requests are not new tasks.

Apply `task` and `skill` at each new user task. Apply `subagent` immediately before each otherwise-planned spawn, using that child's work. Follow-ups, clarification answers, and resuming a pending task reuse its choices; reroute when its scope changes or the user requests it. Explicit user model or skill choices and mandatory workflows take precedence for their respective decision. Other enabled decisions still apply.

An off decision follows normal host behavior. Enabling `subagent` selects models for planned agents; it does not create agents, choose their number, or expand their permissions. A skill runs after turn dispatch and cannot guarantee pre-turn interception; a strict guarantee requires host-side integration.

## Route

1. **Scope.** Identify the event and its enabled decisions. At a user task, consider `task` and `skill`; at a planned spawn, consider `subagent` and any enabled skill selection for that child's work. Skip decisions already fixed by explicit instructions. If none remain, use normal host behavior without calling Jev. Done when each requested decision has a target and a task summary.
2. **Inventory.** Read [candidate and host guidance](references/hosts.md). Obtain live IDs and descriptions separately for each domain: this conversation's models, implicitly invocable skills, or models accepted by the planned spawn tool. Exclude Jev itself from skill candidates. Request missing task-model inventory from the user's picker; for unavailable skill or spawn inventory, report the limit and use ordinary selection or inheritance. Done when every supplied candidate is verified for its own domain.
3. **Ask.** Prepare stdin using [request guidance](references/requests.md). Batch decisions about the same work in one call; a child's summary gets a separate request when that spawn is planned. Include only enabled, applicable domains. Send a sanitized summary of complexity, modalities, and preferences plus candidate descriptions; no credentials, private paths, repository content, or conversation history. Done when every requested answer validates or the helper returns an explicit error.
4. **Apply.** Apply the branches below. Store choices with the pending task; apply its task model before executing its selected skill. Confirm model application through host metadata or the user, and report each applied choice once. Done when the task or spawn proceeds with confirmed choices, ordinary fallback, or a visible pending manual switch.

On a missing key, timeout, HTTP failure, or invalid response, apply none of that batch's answers. Report the failed decisions and use the current task model, ordinary skill workflow, or inherited child model unless the user required successful routing. Preserve the enabled set. A recommendation alone is not a completed switch or invocation.

## Task model

If the recommendation matches the verified current model, continue. Otherwise use [host-specific switching](references/hosts.md#codex) and verify it before claiming success. Codex Desktop's `send_message_to_thread(model)` changes the same thread's next-turn model only; it cannot change an active turn. When this capability and the current thread ID are available, submit the selected model once to the current thread, mark the decision consumed, and verify the next turn's model metadata. Keep a compact pending-task summary and its choices across that handoff; do not include private task data in the handoff message or reroute on it. Preserve the current effort only if the selected model supports it; otherwise use a compatible effort reported by the host. If the task needs the recommended model before it can execute, leave it pending until a model-overridden turn can start. If switching is user-only, report the model and confidence and wait for the user to switch in the original conversation. A startup flag, config edit, or separate process does not switch this conversation.

## Skill

Choose at most one optional primary skill. A `null` choice adds none; mandatory skill rules still apply. Recheck the chosen skill's current invocation policy, load its `SKILL.md`, and follow it within existing authorization. Skills marked `disable-model-invocation: true` or `policy.allow_implicit_invocation: false` require explicit user invocation and stay outside Jev's automatic candidates. Enabling skill routing does not override those policies. A user-selected skill remains selected without another Jev skill decision. Pass a child's skill choice in its brief for that child to load and follow.

## Subagent model

Ask before each actual spawn, after defining that child's goal and constraints. Pass the validated model in the spawn tool's supported model field; preserve compatible reasoning settings. Where model overrides require fresh context, supply a self-contained brief if the workflow permits it. Otherwise report the constraint and retain inheritance. A rejected model falls back to inheritance with a visible routing failure; create no replacement chat or CLI process.

Include the intended model and any selected child skill in the child brief; the spawn request is application evidence, while host-reported runtime metadata is verification when available. Pass enabled decisions and preferences explicitly if children may delegate again; fresh child context otherwise lacks them. Mark the child's initial model and skill choices as already consumed so it applies them without rerouting on startup. Follow-ups to an existing agent do not create a new spawn decision.
