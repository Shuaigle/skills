# Native Claude Code routing

Load this repo as a Claude Code plugin on version **2.1.287 or later**. The plugin's mod routes planned subagent models; symlinking the skill alone does not load it. For development, start Claude Code from the repo with:

```sh
claude --plugin-dir .
```

The user controls that session with `/jev on [skill subagent]`, `/jev on all`, `/jev off [decisions]`, and `/jev status`. Bare `/jev on` and `/jev on all` enable both decisions. Only explicit human commands change the enabled set; enabled decisions then run automatically in that conversation. Native commands own the flags and report them as context; use that state instead of a second skill-only state. The flags start off, stay in memory, and reset when the module reloads or the session ends. Plugin trust or organization policy may require approval to load the mod; successful routing does not ask for each child-model choice.

## What runs automatically

With only `subagent` enabled, the mod obtains live model options from the native configuration menu, filters unavailable or virtual modes, asks Jev before an existing `agent.spawn`, and passes its chosen ID or alias in the spawn's `model` field. Leave `Agent.model` unset in this branch except for an explicit user choice. Native status distinguishes its requested child model from the model reported by the host. A stable host tool-use ID and parent-agent ID identify that spawn's cached decision or failure; repeated events reuse it, while separate spawns remain separate even when their prompts match. Without a stable ID, the mod reports the limit and routes that event once.

With both `skill` and `subagent` enabled, the agent prepares the child's goal and live eligible inventories, then calls the helper once with both domains. Cache that unit's success or failure through its continuations. Put the validated model in `Agent.model` and selected skills in the self-contained brief; the native hook preserves the supplied model. A failed preparation leaves the model unset and uses inheritance. The mod makes no second Jev call in this branch. It has no native skill-policy inventory or validated receipt API, so combined preparation relies on the agent following this workflow.

For local work, or children with only `skill` enabled, the agent selects zero or more optional skills once per independent unit and reuses them through its continuations. Native context points to the installed instructions. Mandatory workflows and user-invoked skill restrictions still apply. A fork inherits its parent; a supplied model remains fixed. The mod creates no additional agents and leaves permissions unchanged.

## Data and failure behavior

Native model-only routing sends locally extracted work categories, length/complexity buckets, and modality/risk markers to Jev. It sends no raw prompt, code, conversation history, or private paths. This summary is less detailed than one prepared by the agent. Model IDs and descriptions come from the host's offered options; private provider identifiers are omitted. Agent-prepared combined requests follow the skill's same sanitization rules.

The Python helper inherits `JEV_API_KEY`; the mod passes no key in command arguments or stdin. Routing failures retain the spawn's inherited model. A downstream model or tool failure is not replayed. Missing inventory, a locked model configuration, a refused mod, or an unsupported Claude version is reported as a limit, never as an applied model. The parent keeps its configured model.

Sources: [mod creation and version requirements](https://code.claude.com/docs/en/plugins/mods/create), [subagent spawning](https://code.claude.com/docs/en/plugins/mods/reference#subagents).
