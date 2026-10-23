---
name: jev
description: Jev routing for optional skills and subagent model/effort pairs.
disable-model-invocation: true
---

# Jev

Start Jev only through an explicit human invocation or Jev control command. After the user enables decisions, continue their routing in this conversation under that authorization. Agents and other skills cannot invoke Jev or enable its decisions on their own.

Let Jev choose zero or more optional skills and a planned subagent's model and reasoning effort from live, supported combinations. Enable each decision independently; reuse each independent work unit's decisions through its batch and continuations.

In Codex with this plugin's hooks loaded, read [Codex routing](references/codex-native.md). Human commands own the flags; before covered work tools, declare each independent unit through the emitted `begin` command. It caches the routing result and applies prepared child-model and effort choices. Use the hook's state instead of a second skill-only state.

In Claude Code with this plugin's native mod loaded, read [Claude routing](references/claude-native.md). Its `/jev` commands own the flags. With only `subagent` enabled, the mod owns child model and effort routing and reports the applied effort as unverified. With both decisions enabled, prepare one child batch here and submit it through the emitted `claude_route.py begin` command; apply the receipt's model and effort through the spawn fields and copy its `brief_line` and skills into the brief. The mod denies a spawn without a matching receipt and makes no second Jev call. Follow the emitted native context. Other hosts retain the workflow below.

## Control

Keep an `enabled_decisions` set, routing preferences, and work-unit choices in this conversation. Valid decisions are `skill` and `subagent`. A new conversation starts with both **off**. Codex hooks keep a private conversation cache; other paths keep runtime state in memory.

| Request | Action | Done when |
|---|---|---|
| `jev on [decisions]` | Add the named decisions; bare `on` and `on all` enable both. Check `JEV_API_KEY` presence without displaying it; a missing key or unknown decision leaves the set unchanged. | Report both flags and conversation scope. Route accompanying work next. |
| `jev off [decisions]` | Remove the named decisions; bare `off` or `off all` clears the set. Clear choices for disabled decisions. | Report both flags. Disabled decisions make no Jev requests. |
| `jev status`, or `jev` alone | Report both flags, active work-unit choices, and any native model exclusions. | Make no API request. |
| `jev exclude <models...>` — Claude native only | Exclude the named models in this conversation. Requires a human command; changes no routing flags and needs no API key. | Native status reports the exclusions. |
| `jev include <models...>` — Claude native only | Remove those native exclusions. Changes no routing flags and does not verify restored credits. | Native status reports the remaining exclusions. |

For example, `jev on subagent` enables child-model and effort routing from the default off state; `jev off skill` disables only optional skill selection. Effort belongs to `subagent`, not a separate enable scope. Configuration requests are not new work units.

Claude native exclusions change only through human `exclude`/`include` commands. Runtime credit errors leave that list unchanged. While `subagent` is on, filtering and checks apply to new planned children; resume, fork, and workflow paths retain host behavior. Off retains the list, and a new session or module reload clears it. Other hosts follow human model constraints without gaining these native commands.

Apply `skill` once per independent local work unit. Apply `subagent` and any enabled `skill` selection once per planned child's work. Ten file reads and their summary can be one unit; editing or verifying a different goal starts another. Reuse decisions for repeated reads, follow-ups, clarifications, and resuming the same unit. Changed goals, candidates, preferences, or enabled decisions need a new unit. Explicit user model, effort, or skill choices and mandatory workflows constrain their respective decisions. Other enabled decisions still apply.

An off decision follows normal host behavior. Enabling `subagent` selects a supported model/effort pair for planned agents; it does not create agents, choose their number, or expand their permissions. A skill alone relies on the agent following these steps. Codex hooks guard covered work-tool paths; the agent still defines the semantic boundaries between units.

## Route

1. **Scope.** Identify the independent unit and its enabled decisions. For local work, consider `skill`; at a planned spawn, consider `subagent` and any enabled skill selection for that child's work. Reuse an existing unit's choices and keep explicit choices fixed. If no decisions apply, use normal host behavior without calling Jev. Done when each requested decision has a target and a bounded work summary.
2. **Inventory.** Read [candidate and host guidance](references/hosts.md). Obtain live IDs and descriptions for implicitly invocable skills and supported child model/effort combinations. Tool options and policy allowlists prove support, not remaining credits. Apply human model exclusions; unknown quota remains eligible and is reported as unverified. Exclude Jev and already-fixed skills from optional candidates. Narrow combinations to any explicitly chosen model or effort. Where the host permits model-only fallback for unavailable effort capability, retain verified models and report that effort stays host-controlled. For unavailable model or skill inventory, use ordinary selection or spawn defaults. Done when every supplied candidate and capability limitation is accounted for.
3. **Ask.** Prepare stdin using [request guidance](references/requests.md), or the Codex `begin` contract when hooks own routing. Batch decisions about the same work in one call; a child's summary gets a separate request when that spawn is planned. Include only enabled, applicable domains. Send a sanitized summary of complexity, modalities, and preferences plus candidate descriptions; no credentials, private paths, repository content, or conversation history. Done when every requested answer validates or the helper returns an explicit error.
4. **Apply.** Apply the branches below and store choices with the unit. Report each applied choice once. Done when selected skills are loaded and a planned spawn carries its validated model/effort pair, or a routing failure has a visible ordinary fallback.

On a missing key, timeout, HTTP failure, or invalid response, apply none of that batch's answers. Report the failed decisions and use ordinary skill workflow or the original spawn settings unless the user required successful routing. Preserve the enabled set. A recommendation alone is not an applied model, effort, or skill.

## Skill

Apply every eligible skill in `decisions.skill.choices`; an empty list adds no optional skills. Mandatory skill rules still apply. Recheck each selected skill's current invocation policy, load each `SKILL.md`, and follow them within existing authorization. Resolve conflicting instructions by their precedence and report any selection that cannot be applied. Skills marked `disable-model-invocation: true` or `policy.allow_implicit_invocation: false` require explicit user invocation and stay outside Jev's automatic candidates. Enabling skill routing does not override those policies. User-selected skills remain selected without another Jev skill decision. Pass a child's selected skills in its brief for that child to load and follow.

## Subagent model and effort

Ask before each actual spawn, after defining that child's goal and constraints. Treat the chosen option as one atomic model/effort pair; `.choice` is an option ID, not a model ID. When the user has enabled `subagent` and the pair is verified, this skill explicitly requires applying Jev's exact returned `model` and concrete `effort` to that spawn. The agent does not independently choose an effort level. A null effort leaves per-spawn effort unset: report default-only behavior or the host-specific model-only fallback, including any missing effort capability. Where overrides require fresh context, supply a self-contained brief if the workflow permits it. Otherwise report the constraint and retain the original spawn settings. A rejected pair uses a visible fallback; create no replacement chat or CLI process.

Recheck current human model exclusions immediately before dispatch, including prepared or cached choices. A changed exclusion invalidates a blocked choice; retain selected skills and the brief, then use a new routing unit or revision with updated candidates. Let Jev choose again for a newly planned attempt instead of silently substituting a model. The native integration never replays failed work automatically; establish the outcome of possibly side-effecting work before any repeat.

If the user fixed an effort but the per-model capability matrix is unavailable, preserve that effort and the original child model, report the constraint, and route remaining optional skills normally. Change the model under a fixed effort only when a trustworthy matrix verifies the combination.

Include the intended model, effort, and selected skills in the child brief; the spawn request is application evidence, while host-reported runtime metadata is verification when available. Pass the user's authorized enabled decisions, preferences, and routing instructions explicitly if children may delegate again; fresh child context otherwise lacks them. Children continue that authorization without invoking Jev as a new skill. Mark the child's initial choices as already consumed so it applies them without rerouting on startup. Follow-ups to an existing agent do not create a new spawn decision.
