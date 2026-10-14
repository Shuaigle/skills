# Host discovery and switching

Use capabilities exposed by the active host. A skill cannot give itself a model-switch tool or control the turn that already dispatched it. User-only commands are instructions for the user, not shell commands for the agent.

## Separate candidate domains

Task models come from the current conversation's selectable models. Subagent models come from the planned spawn tool's accepted models and context constraints. A model supported for a new standalone chat or the parent conversation is not proof that a spawn tool accepts it. Keep these inventories separate even when their IDs overlap.

Skill candidates come from the active host's current skill catalog. Keep its exact invocation IDs, including namespaces needed to distinguish duplicate short names. Inspect frontmatter and `agents/openai.yaml` when invocation policy is absent from catalog metadata; include only skills whose current policy permits implicit invocation. Omit unknown or inaccessible policies. Exclude Jev to prevent routing recursion. Strip personal paths, private IDs, and credentials from descriptions before sending them; retain the skill's purpose and triggers, not its full instruction body.

A skill choice is permission to apply an eligible workflow within the existing task. It does not authorize external messages, commits, deletion, or other actions the user has not authorized.

## Codex

When the Codex plugin hooks are loaded and trusted, use [Codex routing](codex-native.md) for human controls, unit declarations, decision reuse, and prepared subagent spawns. Symlinking this skill alone does not install hooks. Hook output has no documented main-model override; use the switching capabilities below for a pending task-model choice.

Prefer model metadata supplied for the current host and conversation. A client that already controls the conversation through [Codex app-server](https://learn.chatgpt.com/docs/app-server) can call `model/list`; consume every `nextCursor` and retain only selectable models. Include descriptions and required capabilities; keep reasoning effort compatible with the chosen model.

In Codex CLI, inspect the installed `codex debug models --help`, then use `codex debug models` if supported. Inspect its current schema and visibility/availability fields before constructing candidates. `--bundled` skips refresh, so it is unsuitable as proof of current availability. A different CLI installation's catalog does not establish the Desktop conversation's choices. If the active host exposes no inventory, ask the user for the current model picker's selectable rows.

If automatic switching is unavailable, use the original conversation's model picker. In CLI, open `/model`, select the recommendation, and check `/status`. In Desktop, ask the user to select it in that conversation. Report **recommended, awaiting switch** until confirmed.

In Codex Desktop, when `send_message_to_thread` is available, get the exact current thread ID from trusted host context. If it is absent, use the app's thread inventory only when current project and title identify one unique active thread; otherwise use the manual fallback. Its `model` argument updates that thread's **next-turn** model. Preserve a compatible reasoning effort. Sending to the current thread while it is active does not change the running turn; the message is delivered to that turn and the model applies on a later turn. Send at most once for a routing decision, mark it consumed, and verify the later turn's model metadata. A returned thread ID or an updated picker alone is not proof that inference used the target. If the task must run under the target model immediately, preserve it as pending; the current Desktop tools cannot queue a model-overridden turn after the active turn completes. Do not steer another thread or create a replacement chat.

An app-server client that owns this thread can set `model` on a subsequent `turn/start`. A skill cannot attach a second app-server to the running Desktop conversation. Startup `--model` and editing config do not switch it. `turn/steer` cannot change the running turn's model.

Sources: [CLI commands](https://learn.chatgpt.com/docs/developer-commands?surface=cli), [app-server](https://learn.chatgpt.com/docs/app-server).

For Codex subagents, inspect the currently exposed spawn tool's schema. Use its own accepted model list and pass the selected ID in its model field. Some harnesses allow overrides only for fresh-context spawns; provide a self-contained brief and the required context option when the workflow permits that mode. A full-history spawn restricted to inheritance keeps its inherited model unless the user or workflow permits changing the context mode. Report an unsupported override instead of claiming it was applied. `create_thread` creates a user-owned chat; it is not a substitute for a subagent spawn.

## Claude Code

When this plugin's native mod is loaded on a supported version, use [native Claude routing](claude-native.md) before the manual fallback below. It rewrites the current turn's actual model requests and planned subagent spawns; it does not replace the conversation or edit global defaults. Task and subagent model choices are then owned by the mod, while this skill still handles optional skill selection.

Use the active session's model metadata or `/model` picker. Account, provider, and organization restrictions determine which rows are selectable. Omit disabled rows; a public Anthropic model catalog is insufficient. Preserve provider-specific IDs or aliases exactly as the session accepts them, and supply the picker's capability descriptions. If the agent cannot read the picker, ask the user for its selectable rows.

For a manual switch, tell the user to open `/model`, select the recommended row, and use the picker's **session-only** action (`s` in versions documenting that binding). Verify with `/status` or the user's confirmation. Read the installed picker/help if its controls differ. Direct `/model <name>` can save a default for future sessions; this skill's scope is the current conversation.

A static skill `model` field is evaluated when the host loads the skill; it cannot apply a later Jev answer dynamically. A classic `UserPromptSubmit` shell hook can add context or block a prompt, but its documented output has no main-model override. Native mods provide separate `turn.step` and `agent.spawn` rewrite points. Without that mod or another exposed switch tool, retain the manual handoff.

Sources: [model configuration](https://code.claude.com/docs/en/model-config), [skills](https://code.claude.com/docs/en/skills), [hooks](https://code.claude.com/docs/en/hooks).

For Claude subagents, inspect the current delegation tool or agent configuration's supported model field and aliases. Its accepted models can differ from the main conversation's picker. Supply a model only through a supported per-spawn override; if selection is fixed in agent configuration, report the constraint and retain that configuration. Editing global settings or an agent definition does not establish a one-spawn override.

## Other hosts

Query the current host's model-list capability and keep its identifiers, descriptions, and access restrictions. Use a switch tool only when its documented scope is this conversation, then read back the selected model. If either capability is missing, request the native picker list or hand off the switch to the user. Keep the original task pending; create no replacement conversation or CLI execution.
