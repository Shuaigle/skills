# Native Claude Code routing

Load this repo as a Claude Code plugin on version **2.1.287 or later**. The plugin's shipped mod handles model requests in the same conversation; symlinking the skill alone does not load it. For development, start Claude Code from the repo with:

```sh
claude --plugin-dir .
```

In that session, use `/jev on task`, `/jev on subagent`, `/jev on all`, `/jev off [decisions]`, and `/jev status`. Native commands own the enabled set and report it as context; use that state instead of maintaining a second skill-only set. The flags start off, stay in memory, and reset when the module reloads or the session ends. Plugin trust or organization policy may require one-time approval to load a mod; successful routing does not ask for each model choice.

## What runs automatically

At a main turn, the mod obtains the current model options from the native configuration menu and removes virtual modes and unsupported options. Main requests need full model IDs: the local Claude CLI resolves offered aliases with the built-in `/status` command in bare mode, without inference, credentials, plugins, or session persistence. Jev receives the resolved candidates; `turn.step.model` applies its choice to that turn's requests. No model versions are hardcoded. The original transcript stays in place; the session's saved `/model` default is not rewritten. The requested model and the model reported by `usage.model` are distinct evidence and appear in routing status.

The resolver uses `claude` on `PATH` and checks that its version matches the running host; `JEV_CLAUDE_BINARY` may point to the matching executable when needed. Probe configuration lives in a temporary directory and does not change user settings. Unresolved or private provider model IDs are omitted. An explicit leading `Use <offered-model> for this task: ...` or `這個任務使用 <offered-model>：...` takes precedence over Jev; an incidental model mention does not.

Before an existing `agent.spawn`, the mod asks Jev about that child's work and passes the choice in the spawn's `model` field. Native context tells the agent to leave `Agent.model` unset when Jev controls subagents, except for an explicit user choice. A fork inherits its parent and ignores model overrides; a spawn with a model already specified retains that choice. The mod creates no additional agents and leaves permissions unchanged.

`skill` remains an agent-mediated workflow: native context tells the agent to use the Jev skill to select zero or more optional skills. The mod handles task and subagent models, so the agent must skip duplicate model routing and manual model-switch waits. Mandatory workflows and user-invoked skill restrictions still apply.

## Data and failure behavior

The native path sends locally extracted work categories, length/complexity buckets, and modality/risk markers to Jev. It sends no raw prompt, code, conversation history, or private paths. This summary is less detailed than one prepared by the agent. Model IDs and descriptions come from the host's offered options; private provider identifiers are omitted.

The Python helper inherits `JEV_API_KEY`; the mod passes no key in command arguments or stdin. Routing failures retain the original request's model. A downstream model or tool failure is not replayed. Missing inventory, a locked model configuration, a refused mod, or an unsupported Claude version is reported as a limit, never as a successful switch.

Sources: [mod creation and version requirements](https://code.claude.com/docs/en/plugins/mods/create), [turn request rewriting](https://code.claude.com/docs/en/plugins/mods/events#follow-a-turn), [subagent spawning](https://code.claude.com/docs/en/plugins/mods/reference#subagents).
