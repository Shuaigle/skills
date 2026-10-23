# Native Claude Code routing

Load this repo as a Claude Code plugin on version **2.1.287 or later**. The plugin's mod routes planned children; symlinking the skill alone does not load it. The separate built-in Agent tool's per-invocation effort field requires **2.1.292 or later** and a non-fork spawn. Native effort routing through `turn.step` was verified on 2.1.302. For development, start Claude Code from the repo with:

```sh
claude --plugin-dir .
```

The user controls that session with `/jev on [skill subagent]`, `/jev on all`, `/jev off [decisions]`, and `/jev status`. Bare `/jev on` and `/jev on all` enable both decisions. Only explicit human commands change the enabled set; enabled decisions then run automatically in that conversation. Native commands own the flags and report them as context; use that state instead of a second skill-only state. The flags start off, stay in memory, and reset when the module reloads or the session ends. Plugin trust or organization policy may require approval to load the mod; successful routing does not ask for each child-model choice.

## Manual model exclusions

Model enums, the configuration menu, and organization `availableModels` establish support or policy eligibility, not current credits. This mod has no verified per-model live quota API. Unknown quota stays eligible. Runtime credit errors do not update the exclusion list automatically; after a failure, the user can exclude that model and later include it again.

Only human `/jev exclude <models...>` and `/jev include <models...>` commands add or remove exclusions. They change no enabled flags and need no `JEV_API_KEY`. Use public host model IDs or aliases. Known aliases `sonnet`, `opus`, `haiku`, and `fable`, including their recognized public model-version IDs, share family exclusions: excluding or including one affects the entire family. Other accepted public IDs use exact matching. Include removes the local exclusion without confirming restored credits.

Status and emitted context list the human exclusions. Agent-prepared combined batches remove every matching model/effort option. For new planned children, the native path filters options and checks prepared, native-selected, and cached choices immediately before dispatch. A blocked choice is reported; the mod never silently substitutes another model or automatically replays the spawn. Resume, fork, and host-owned workflow paths pass through unchanged; these checks do not guard their inherited models.

Retain selected skills and the brief when human exclusions change. A newly planned attempt uses a new routing unit or revision and lets Jev select from updated candidates. Establish what possibly side-effecting failed work actually did before repeating it. Routing and dispatch checks stop whenever `subagent` is off, including skill-only mode; off retains the list. A new session, module reload, or session end clears it.

## What runs automatically

With only `subagent` enabled, the mod obtains currently offered models from the native configuration menu, applies policy and session exclusions, removes virtual modes, and submits atomic options before an existing `agent.spawn`. Offered does not mean quota-verified. Each option pairs a model with one of `low`, `medium`, `high`, `xhigh`, `max`. `agent.spawn` accepts only a model, so the mod applies the selected model there, maps the returned `agentId` to the selected effort, and rewrites `effort` in that child's `turn.step` model requests. A child's request that arrives before its spawn answers waits up to 3 seconds for the mapping. Main-conversation requests and unmapped children are unchanged. Leave `Agent.model` and `Agent.effort` unset in this branch except for an explicit user choice.

The mod API exposes no per-model effort matrix. The host sends no effort to a model without one and silently lowers an unsupported level; no hook sees the result. Classic hook `effort.level` reports the child's effort before the `turn.step` rewrite, so it cannot verify application. Native status reports the requested and host-reported model, the requested effort, and the actual effort as `unverified`, or `none` when the model takes no effort.

`agent.spawn` does not carry the Agent tool's `effort`; the mod reads it from the parent's `tool.call` for that tool-use ID. An explicit `Agent.effort` keeps the host dispatch without a Jev call. With `CLAUDE_CODE_EFFORT_LEVEL` set, or without a stable spawn ID to check for an explicit effort, options use `effort: null`: the mod routes the model only and reports effort as locked or host-controlled. An agent definition's own effort is not visible to the mod and the selected effort overrides it.

A stable host tool-use ID and parent-agent ID identify that spawn's cached decision or failure; repeated events reuse it, while separate spawns remain separate even when their prompts match. Without a stable ID, the mod reports the limit and routes that event once. Returned model and effort must match the selected opaque option; an invalid mapping falls back and caches that failure.

Resuming an existing Agent keeps its `agentId`, so the child keeps its model and selected effort without another Jev decision. A running child keeps its pair after `/jev off`; the session end clears the mapping. Native workflow spawns share tool-use IDs across their run, so this mod passes them through and reports its independent-unit identification limit. It does not count those workflow children as routed.

With both `skill` and `subagent` enabled, prepare the child's goal, live eligible skills, and supported options, then call the helper once with both domains. Use concrete model/effort pairs when verified. If the per-model effort matrix is unavailable, keep verified model candidates with `effort: null` in the same batch as skills; this is an explicit model-only fallback, reported as effort not routed. Call it through the receipt helper below, not `route.py` directly. Put the validated model in `Agent.model`, its exact concrete effort in `Agent.effort` when verified, and skills in the brief. Null leaves the per-spawn effort unset for host defaults. The native hook makes no second Jev call; it verifies the receipt and dispatches the prepared spawn unchanged. It has no native skill-policy inventory, so candidate preparation still relies on the agent.

The built-in Agent tool supports per-invocation effort on supported versions, but its raw effort enum is not a model/effort matrix. In agent-prepared batches, include concrete options only with trustworthy live evidence for that exact model and dispatch path; never form the Cartesian product of all models and effort values. The native-only path above forms that product because it reports the actual effort as unverified. Unknown effort capability does not make the model unsupported. Model-only fallback preserves model and skill routing without claiming effort was selected. It cannot be mixed with concrete effort options for that same model.

If the user fixed an effort and no trustworthy matrix verifies it, retain that effort and the original child model, report the constraint, and route optional skills normally. A verified matrix instead narrows candidates to combinations matching the fixed effort. `CLAUDE_CODE_EFFORT_LEVEL` sets every agent's effort; account for that constraint before listing options and report any unapplied choice. An API failure still invalidates the entire batch and retains the original spawn settings.

## Combined routing receipts

While both decisions are on, every new non-fork, non-resume, non-workflow spawn needs a receipt. Before the spawn, run `python3 '<plugin root>/skills/jev/scripts/claude_route.py' begin` with JSON stdin; the native context prints the exact path and session ID, and `--help` lists the fields:

- `session_id`: from the native context. It may be omitted when `CLAUDE_CODE_SESSION_ID` is set and must match it otherwise.
- `original`: `{model, effort}` the spawn would use without Jev, each null when unset.
- `request`: one [routing request](requests.md) for this child with a `skill` decision (an empty list is valid) and a `subagent` decision.
- `skip_subagent`: required exactly when `request` has no `subagent` decision: `fixed_effort_unverified` (the user fixed an effort that no matrix verifies) or `inventory_unavailable`. Skills are still routed and `original` applies.

The helper calls the router in-process and prints `receipt_id`, `model`, `effort`, `skills`, `status`, and a `brief_line` such as `Jev routing: {"receipt":"r-…","model":"haiku","effort":"low","skills":["testing"]}`. Copy that line verbatim as one line of the Agent prompt, set `Agent.model` and `Agent.effort` from it, omitting each when null, and pass the skills to the child. A routing failure (missing key, network, HTTP, invalid response) returns `status: fallback` with its `code`, ordinary skills, and `original`; report it and dispatch with those settings. Invalid or unsafe input writes no receipt and exits 1, so a skipped route and a failed route stay distinguishable.

At `agent.spawn` the mod finds the single `Jev routing:` line and runs the helper's `claim` with this session's ID, the stable spawn key, `Agent.model`, the `Agent.effort` from the parent's `tool.call`, and the line. It denies the spawn, naming the `begin` command, when the prompt has no line or several, the receipt does not exist in this session, is older than 30 minutes, belongs to another spawn, or its line, model, or effort differs; mismatches print the expected values. A refused claim consumes nothing. A matching claim binds the receipt to that spawn; repeated events of the same spawn reuse it and status reports `receipt=`, the pair, skills, and `routing=recommended` or `fallback(<code>)`. Manual exclusions still block a receipt's model. If the helper itself cannot run, the spawn is denied; the user can run `/jev off skill` to leave combined routing.

Receipts live in a per-user private temporary directory (`JEV_CLAUDE_STATE_DIR` overrides it when both the agent shell and the mod see it), one file per session keyed by a digest. Each holds status, failure code, model, effort, skill IDs, the brief line, creation time, and the claiming spawn's digest; no API key, task text, prompt, raw session ID, or spawn ID. `begin` prunes expired receipts; consumed receipts stay consumed across module reloads. A child that may delegate needs the command and session ID in its brief. The receipt proves the router ran for this spawn; it does not stop an agent that forges files on purpose.

`route.py` stays stateless: the native-only path and the Codex gate call it without receipts.

## Skill-only and local work

For local work, or children with only `skill` enabled, the agent selects zero or more optional skills once per independent unit and reuses them through its continuations. Native context points to the installed instructions. Mandatory workflows and user-invoked skill restrictions still apply. A fork inherits its parent; a supplied model remains fixed. The mod creates no additional agents and leaves permissions unchanged.

## Data and failure behavior

Native routing sends locally extracted work categories, length/complexity buckets, and modality/risk markers to Jev. It sends no raw prompt, code, conversation history, or private paths. This summary is less detailed than one prepared by the agent. Model IDs and descriptions come from the host's offered options; private provider identifiers are omitted. Agent-prepared combined requests follow the skill's same sanitization rules.

The Python helper inherits `JEV_API_KEY`; the mod passes no key in command arguments or stdin. Routing failures retain the original spawn settings. A downstream model or tool failure is not replayed. Missing inventory, a locked model configuration, a refused mod, or an unsupported Claude version is reported as a limit, never as an applied model or effort. The parent keeps its configured model.

Sources: [mod creation and version requirements](https://code.claude.com/docs/en/plugins/mods/create), [native subagent spawning](https://code.claude.com/docs/en/plugins/mods/reference#subagents), [Agent tool effort support and precedence](https://code.claude.com/docs/en/sub-agents#choose-an-effort-level).
