# Host candidates and subagents

Use capabilities exposed by the active host. Jev selects optional skills and a planned child's model/effort pair; the parent keeps its configured model.

## Separate candidate domains

Subagent model/effort combinations come from the planned spawn tool's live accepted models, per-model efforts, and context constraints. A model or effort supported by the parent conversation is not proof that a spawn accepts it. Build only verified combinations; preserve exact host field values and capability descriptions. An opaque option ID identifies each pair in [routing requests](requests.md).

Support and policy eligibility are separate from current credits. A tool enum, configuration menu, or organization `availableModels` allowlist does not verify quota. Unknown quota remains eligible without a promise of successful dispatch. Apply explicit human model constraints; in Claude native, only human `exclude`/`include` commands change the exclusion list. Runtime errors do not change it automatically.

Use concrete effort values only for verified per-model combinations. Null means host-controlled effort: default-only behavior, absent per-spawn control, or an explicit model-only fallback supported by that host's routing path. Missing effort capability does not invalidate a verified model. Report model-only fallback as effort not routed, and retain model and skill routing where supported. Codex gates retain their stricter required-matrix validation. Never mix null and concrete options for the same model or multiply a global effort enum by every model.

Explicit user model or effort constraints narrow verified combinations; a fixed model can still offer several effort choices. If the user fixed effort and the matrix is unavailable, keep that effort and the original child model. Report the capability limit and route remaining optional skills; only a verified matching combination permits changing models.

Skill candidates come from the active host's current skill catalog. Keep its exact invocation IDs, including namespaces needed to distinguish duplicate short names. Inspect frontmatter and `agents/openai.yaml` when invocation policy is absent from catalog metadata; include only skills whose current policy permits implicit invocation. Omit unknown or inaccessible policies. Exclude Jev to prevent routing recursion. Strip personal paths, private IDs, and credentials from descriptions before sending them; retain the skill's purpose and triggers, not its full instruction body.

A skill choice is permission to apply an eligible workflow within the existing task. It does not authorize external messages, commits, deletion, or other actions the user has not authorized.

## Codex

When the Codex plugin hooks are loaded and trusted, use [Codex routing](codex-native.md) for human controls, unit declarations, decision reuse, and prepared subagent spawns. Symlinking this skill alone does not install hooks.

The Codex gate validates model/effort capability combinations and routing receipts; it does not check credits or implement Claude's native exclusion commands. Apply human model constraints while preparing candidates.

For Codex subagents, inspect the currently exposed spawn tool's model and `reasoning_effort` fields plus its supported per-model combinations. Apply the chosen model and effort together. Some harnesses allow overrides only for fresh-context spawns; provide a self-contained brief and the required context option when the workflow permits that mode. A full-history spawn restricted to inheritance keeps its original settings unless the user or workflow permits changing context mode. Report an unsupported override instead of claiming it was applied. `create_thread` creates a user-owned chat; it is not a substitute for a subagent spawn.

## Claude Code

When this plugin's native mod is loaded on a supported version, use [native Claude routing](claude-native.md). Native commands own the flags. The mod routes children when only `subagent` is enabled; with `skill` also enabled, the agent prepares one combined child batch before spawning.

For Claude subagents, inspect the current delegation tool's model and effort capabilities and accepted aliases. Account, provider, and organization restrictions determine policy eligibility; a public catalog is insufficient. They do not establish remaining credits. Preserve field values exactly as that spawn accepts them and verify effort support for each model. Apply native session exclusions to every effort option for an excluded model. If selection is fixed in agent configuration, report the constraint and retain it. Editing global settings or an agent definition does not establish a one-spawn override.

## Other hosts

Inspect the planned spawn tool's live model/effort inventory and per-spawn fields. If effort capability evidence is unavailable, use model-only fallback only when that host's routing path supports it and report effort as host-controlled. Missing model inventory retains the original spawn settings. Pass a self-contained brief where fresh context is required. Host-reported child metadata verifies the applied pair when available; create no replacement conversation or CLI execution.
