---
name: jev
description: Jev routing for optional skills and subagent models.
disable-model-invocation: true
---

# Jev

Start Jev only through an explicit human invocation or Jev control command. After the user enables decisions, continue their routing in this conversation under that authorization. Agents and other skills cannot invoke Jev or enable its decisions on their own.

Let Jev choose zero or more optional skills and a planned subagent's model from live candidates. Enable each decision independently; reuse each independent work unit's decisions through its batch and continuations.

In Codex with this plugin's hooks loaded, read [Codex routing](references/codex-native.md). Human commands own the flags; before covered work tools, declare each independent unit through the emitted `begin` command. It caches the routing result and applies prepared child-model choices. Use the hook's state instead of a second skill-only state.

In Claude Code with this plugin's native mod loaded, read [Claude routing](references/claude-native.md). Its `/jev` commands own the flags. With only `subagent` enabled, the spawn hook owns child-model routing. With both decisions enabled, prepare one child batch here, put its model in `Agent.model` and skills in the brief; the mod preserves that preparation without another Jev call. Follow the emitted native context. Other hosts retain the workflow below.

## Control

Keep an `enabled_decisions` set, routing preferences, and work-unit choices in this conversation. Valid decisions are `skill` and `subagent`. A new conversation starts with both **off**. Codex hooks keep a private conversation cache; other paths keep runtime state in memory.

| Request | Action | Done when |
|---|---|---|
| `jev on [decisions]` | Add the named decisions; bare `on` and `on all` enable both. Check `JEV_API_KEY` presence without displaying it; a missing key or unknown decision leaves the set unchanged. | Report both flags and conversation scope. Route accompanying work next. |
| `jev off [decisions]` | Remove the named decisions; bare `off` or `off all` clears the set. Clear choices for disabled decisions. | Report both flags. Disabled decisions make no Jev requests. |
| `jev status`, or `jev` alone | Report both flags and any active work-unit choices. | Make no API request. |

For example, `jev on subagent` enables only child-model routing from the default off state; `jev off skill` disables only optional skill selection. Configuration requests are not new work units.

Apply `skill` once per independent local work unit. Apply `subagent` and any enabled `skill` selection once per planned child's work. Ten file reads and their summary can be one unit; editing or verifying a different goal starts another. Reuse decisions for repeated reads, follow-ups, clarifications, and resuming the same unit. Changed goals, candidates, preferences, or enabled decisions need a new unit. Explicit user model or skill choices and mandatory workflows take precedence for their respective decision. Other enabled decisions still apply.

An off decision follows normal host behavior. Enabling `subagent` selects models for planned agents; it does not create agents, choose their number, or expand their permissions. A skill alone relies on the agent following these steps. Codex hooks guard covered work-tool paths; the agent still defines the semantic boundaries between units.

## Route

1. **Scope.** Identify the independent unit and its enabled decisions. For local work, consider `skill`; at a planned spawn, consider `subagent` and any enabled skill selection for that child's work. Reuse an existing unit's choices and keep explicit choices fixed. If no decisions apply, use normal host behavior without calling Jev. Done when each requested decision has a target and a bounded work summary.
2. **Inventory.** Read [candidate and host guidance](references/hosts.md). Obtain live IDs and descriptions separately for implicitly invocable skills and models accepted by the planned spawn tool. Exclude Jev and already-fixed skills from optional candidates. Narrow child-model candidates to an explicitly chosen supported model. For unavailable inventory, report the limit and use ordinary skill selection or model inheritance. Done when every supplied candidate is verified for its own domain.
3. **Ask.** Prepare stdin using [request guidance](references/requests.md), or the Codex `begin` contract when hooks own routing. Batch decisions about the same work in one call; a child's summary gets a separate request when that spawn is planned. Include only enabled, applicable domains. Send a sanitized summary of complexity, modalities, and preferences plus candidate descriptions; no credentials, private paths, repository content, or conversation history. Done when every requested answer validates or the helper returns an explicit error.
4. **Apply.** Apply the branches below and store choices with the unit. Report each applied choice once. Done when selected skills are loaded and a planned spawn carries its validated model, or a routing failure has a visible ordinary fallback.

On a missing key, timeout, HTTP failure, or invalid response, apply none of that batch's answers. Report the failed decisions and use ordinary skill workflow or the inherited child model unless the user required successful routing. Preserve the enabled set. A recommendation alone is not an applied model or skill.

## Skill

Apply every eligible skill in `decisions.skill.choices`; an empty list adds no optional skills. Mandatory skill rules still apply. Recheck each selected skill's current invocation policy, load each `SKILL.md`, and follow them within existing authorization. Resolve conflicting instructions by their precedence and report any selection that cannot be applied. Skills marked `disable-model-invocation: true` or `policy.allow_implicit_invocation: false` require explicit user invocation and stay outside Jev's automatic candidates. Enabling skill routing does not override those policies. User-selected skills remain selected without another Jev skill decision. Pass a child's selected skills in its brief for that child to load and follow.

## Subagent model

Ask before each actual spawn, after defining that child's goal and constraints. Pass the validated model in the spawn tool's supported model field; preserve compatible reasoning settings. Where model overrides require fresh context, supply a self-contained brief if the workflow permits it. Otherwise report the constraint and retain inheritance. A rejected model falls back to inheritance with a visible routing failure; create no replacement chat or CLI process.

Include the intended model and all selected child skills in the child brief; the spawn request is application evidence, while host-reported runtime metadata is verification when available. Pass the user's authorized enabled decisions, preferences, and routing instructions explicitly if children may delegate again; fresh child context otherwise lacks them. Children continue that authorization without invoking Jev as a new skill. Mark the child's initial model and skill choices as already consumed so it applies them without rerouting on startup. Follow-ups to an existing agent do not create a new spawn decision.
