# Native Claude Code routing

Load this repo as a Claude Code plugin on version **2.1.287 or later**. The plugin's mod routes planned children; symlinking the skill alone does not load it. The separate built-in Agent tool's per-invocation effort field requires **2.1.292 or later** and a non-fork spawn. For development, start Claude Code from the repo with:

```sh
claude --plugin-dir .
```

The user controls that session with `/jev on [skill subagent]`, `/jev on all`, `/jev off [decisions]`, and `/jev status`. Bare `/jev on` and `/jev on all` enable both decisions. Only explicit human commands change the enabled set; enabled decisions then run automatically in that conversation. Native commands own the flags and report them as context; use that state instead of a second skill-only state. The flags start off, stay in memory, and reset when the module reloads or the session ends. Plugin trust or organization policy may require approval to load the mod; successful routing does not ask for each child-model choice.

## What runs automatically

With only `subagent` enabled, the mod obtains live models from the native configuration menu, filters unavailable or virtual modes, and submits atomic options before an existing `agent.spawn`. This native spawn interface has no verified effort rewrite field or per-model effort matrix, so its options use `effort: null`. It applies only the selected option's `model`, reports effort as host-controlled, and never claims Jev chose a concrete effort on this path. Another tool on the same host can have different capabilities. Leave `Agent.model` unset in this branch except for an explicit user choice. Native status distinguishes its requested model from the host-reported model.

A stable host tool-use ID and parent-agent ID identify that spawn's cached decision or failure; repeated events reuse it, while separate spawns remain separate even when their prompts match. Without a stable ID, the mod reports the limit and routes that event once. Returned model and effort must match the selected opaque option; an invalid mapping falls back and caches that failure.

Resuming an existing Agent preserves its original model and effort without another Jev decision. Native workflow spawns share tool-use IDs across their run, so this mod passes them through and reports its independent-unit identification limit. It does not count those workflow children as routed.

With both `skill` and `subagent` enabled, prepare the child's goal, live eligible skills, and supported options, then call the helper once with both domains. Use concrete model/effort pairs when verified. If the per-model effort matrix is unavailable, keep verified model candidates with `effort: null` in the same batch as skills; this is an explicit model-only fallback, reported as effort not routed. Cache that unit's result or API failure through its continuations. Put the validated model in `Agent.model`, its exact concrete effort in `Agent.effort` when verified, and skills in the brief. Null leaves the per-spawn effort unset for host defaults. The native hook preserves this preparation and makes no second Jev call. It has no native skill-policy inventory or validated receipt API, so preparation relies on the agent following this workflow.

The built-in Agent tool supports per-invocation effort on supported versions, but its raw effort enum is not a model/effort matrix. Include concrete options only with trustworthy live evidence for that exact model and dispatch path; never form the Cartesian product of all models and effort values. Unknown effort capability does not make the model unsupported. Model-only fallback preserves model and skill routing without claiming effort was selected. It cannot be mixed with concrete effort options for that same model.

If the user fixed an effort and no trustworthy matrix verifies it, retain that effort and the original child model, report the constraint, and route optional skills normally. A verified matrix instead narrows candidates to combinations matching the fixed effort. `CLAUDE_CODE_EFFORT_LEVEL` overrides per-invocation effort; account for that constraint before listing options and report any unapplied choice. An API failure still invalidates the entire batch and retains the original spawn settings.

For local work, or children with only `skill` enabled, the agent selects zero or more optional skills once per independent unit and reuses them through its continuations. Native context points to the installed instructions. Mandatory workflows and user-invoked skill restrictions still apply. A fork inherits its parent; a supplied model remains fixed. The mod creates no additional agents and leaves permissions unchanged.

## Data and failure behavior

Native default-effort routing sends locally extracted work categories, length/complexity buckets, and modality/risk markers to Jev. It sends no raw prompt, code, conversation history, or private paths. This summary is less detailed than one prepared by the agent. Model IDs and descriptions come from the host's offered options; private provider identifiers are omitted. Agent-prepared combined requests follow the skill's same sanitization rules.

The Python helper inherits `JEV_API_KEY`; the mod passes no key in command arguments or stdin. Routing failures retain the original spawn settings. A downstream model or tool failure is not replayed. Missing inventory, a locked model configuration, a refused mod, or an unsupported Claude version is reported as a limit, never as an applied model or effort. The parent keeps its configured model.

Sources: [mod creation and version requirements](https://code.claude.com/docs/en/plugins/mods/create), [native subagent spawning](https://code.claude.com/docs/en/plugins/mods/reference#subagents), [Agent tool effort support and precedence](https://code.claude.com/docs/en/sub-agents#choose-an-effort-level).
