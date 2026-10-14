# Host candidates and subagents

Use capabilities exposed by the active host. Jev selects optional skills and a planned child's model; the parent keeps its configured model.

## Separate candidate domains

Subagent models come from the planned spawn tool's accepted models and context constraints. A model supported for a standalone chat or the parent conversation is not proof that a spawn tool accepts it. Keep exact IDs, capability descriptions, and supported reasoning efforts from that tool's live metadata.

Skill candidates come from the active host's current skill catalog. Keep its exact invocation IDs, including namespaces needed to distinguish duplicate short names. Inspect frontmatter and `agents/openai.yaml` when invocation policy is absent from catalog metadata; include only skills whose current policy permits implicit invocation. Omit unknown or inaccessible policies. Exclude Jev to prevent routing recursion. Strip personal paths, private IDs, and credentials from descriptions before sending them; retain the skill's purpose and triggers, not its full instruction body.

A skill choice is permission to apply an eligible workflow within the existing task. It does not authorize external messages, commits, deletion, or other actions the user has not authorized.

## Codex

When the Codex plugin hooks are loaded and trusted, use [Codex routing](codex-native.md) for human controls, unit declarations, decision reuse, and prepared subagent spawns. Symlinking this skill alone does not install hooks.

For Codex subagents, inspect the currently exposed spawn tool's schema. Use its own accepted model list and pass the selected ID in its model field. Some harnesses allow overrides only for fresh-context spawns; provide a self-contained brief and the required context option when the workflow permits that mode. A full-history spawn restricted to inheritance keeps its inherited model unless the user or workflow permits changing the context mode. Report an unsupported override instead of claiming it was applied. `create_thread` creates a user-owned chat; it is not a substitute for a subagent spawn.

## Claude Code

When this plugin's native mod is loaded on a supported version, use [native Claude routing](claude-native.md). Native commands own the flags. The mod routes children when only `subagent` is enabled; with `skill` also enabled, the agent prepares one combined child batch before spawning.

For Claude subagents, inspect the current delegation tool or agent configuration's supported model field and aliases. Account, provider, and organization restrictions determine availability; a public catalog is insufficient. Preserve IDs or aliases exactly as the spawn tool accepts them. Supply a model through a supported per-spawn override; if selection is fixed in agent configuration, report the constraint and retain that configuration. Editing global settings or an agent definition does not establish a one-spawn override.

## Other hosts

Inspect the planned spawn tool's live model inventory and per-spawn override. If either is unavailable, report the constraint and retain inheritance. Pass a self-contained brief where fresh context is required. Host-reported child metadata verifies the applied model; create no replacement conversation or CLI execution.
