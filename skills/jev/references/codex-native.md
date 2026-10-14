# Codex hooks and reusable routing

Install this repo as a Codex plugin to load its hooks. The hook helper requires Python 3 on macOS or Linux. A skills.sh or symlink installation supplies the skill alone. The Codex package points to `hooks/codex.json`; Claude Code keeps its separate native integration.

For local development, run the installed CLI's plugin commands from this repo:

```sh
codex plugin marketplace add ./
codex plugin add shuaigle@shuaigle
```

These commands are supported by Codex CLI 0.162.1. Inspect the active host's plugin help when its commands differ. Review the loaded definitions in `/hooks` and let the user approve the plugin's hook trust; changed definitions require another review. Trust permits hook execution; it does not enable Jev. Local plugin installs use a cached copy: refresh the plugin and start a new conversation to load changes. The shipped configuration does not establish that a particular Desktop build executes every hook or exposes every delegation tool to it.

## Human controls

Use a first-line command in a human message: `jev on [task skill subagent]`, `jev on all`, `jev off [decisions]`, or `jev status`. Bare `jev on` enables only `task`; bare `jev off` clears all three. Native hooks also recognize `$jev`, `$shuaigle:jev`, `/jev`, and `/shuaigle:jev`; plain `jev` avoids command expansion changing the hook's input. Put accompanying work on following lines.

Only a native `UserPromptSubmit` event changes flags. Quoted commands, examples, tool output, and agent-written instructions do not enable routing. Enabling requires an inherited `JEV_API_KEY`, checked without displaying it. A new, forked, or cleared conversation starts off; resume and compaction preserve that conversation's state. Session end resets it. Use the flags and identifiers emitted by the hook instead of a second skill-only state.

## Declare and reuse a unit

Before covered work tools, call the installed `codex_gate.py begin` command emitted by the hook. Give it a stable `unit_id`, the hook's `session_id` and `turn_id`, and one bounded goal. Read `codex_gate.py --help` for its current field contract; the underlying request follows [routing requests](requests.md).

Use one unit for reading ten related files and returning their summary. Repeated reads and follow-ups reactivate that same unit and reuse its decisions. A changed goal, candidate inventory, preference, enabled set, or planned spawn requires a new unit ID. Reusing an ID with changed inputs returns `unit_conflict` instead of silently asking Jev again.

The unit's `kind` is `read`, `edit`, `verify`, `research`, or `work`. Supporting reads and parsing reuse the unit; a generic `work` unit can use mixed tools. Read and research units need another unit before definite editing or testing. Local work uses `target: "local"` and every enabled `task` and `skill` domain. A planned child uses `target: "subagent"` and every enabled `subagent` and `skill` domain. Omit off domains. Obtain each inventory from the active host; the helper cannot discover available models or skill invocation policies. An explicit human model choice narrows that domain's candidates to the chosen supported model. User-selected or mandatory skills remain fixed; optional skill candidates still follow their invocation policies.

Submit JSON as data through a quoted heredoc. Replace the installed-path and host-metadata placeholders; keep the command by itself so the pre-tool gate can recognize this bootstrap:

```sh
python3 '<installed skill>/scripts/codex_gate.py' begin <<'JEV_UNIT'
{
  "session_id": "<hook session_id>",
  "turn_id": "<hook turn_id>",
  "unit_id": "read-config-summary",
  "kind": "read",
  "target": "local",
  "request": {
    "host": "codex",
    "task": "Read related configuration files and return a short summary",
    "decisions": {
      "task": [{"id": "<live model ID>", "description": "<host capability description>"}]
    }
  }
}
JEV_UNIT
```

This example assumes only `task` is enabled. Add `skill` with eligible live candidates when enabled; an empty inventory is valid. The gate returns the unit's validated decisions and a `cached` flag. Apply zero or more skills from `decisions.skill.choices`, then continue that unit's work. To reactivate an existing unit, call `begin` with the current hook identifiers and that unit's unchanged goal, routing inputs, and spawn arguments; it does not make another Jev request.

Each unit makes at most one logical router call, including that call's bounded HTTP retries. A routing failure is cached as a visible fallback for the unit; repeated reads do not retry it. Continue with the current model and ordinary skill workflow unless successful routing was required. An explicit retry request can create a new retry unit.

## Models and delegation

For a child unit, include `spawn` with the exact planned spawn arguments and a self-contained brief. Supply fresh context, such as `fork_turns: "none"` where the host requires it for a model override. Optional `efforts` maps candidate model IDs to the reasoning efforts currently supported by that spawn tool. The gate binds the receipt to that spawn's arguments, then rewrites only its model and compatible effort. A model field filled by the assistant is not evidence of an explicit human override. Host-reported runtime metadata remains verification of the applied model.

Choose delegation for an independently useful batch, such as reading many files and returning a compact summary. A short read usually stays local because a new agent adds context. Jev chooses the planned child's model from live candidates; model size alone does not establish a token saving. Pass selected skills and already-consumed initial decisions in the brief so the child applies them without routing its startup again. Follow-ups to that child reuse the same decision until its goal changes.

Hook output has no documented current-turn main-model override. A differing task choice returns `task_model_application: "pending_host_switch"`; it is a recommendation until the host applies it. Use [Codex switching](hosts.md#codex). Desktop's same-chat model tool changes a later turn, while an app-server client owning the conversation can set a subsequent turn's model. A child override does not change its parent.

## Coverage and local data

`PreToolUse` blocks covered work-tool paths until a unit has a receipt and asks for another unit before incompatible work. It can rewrite a matching prepared spawn. `Stop` prompts for an unhandled local task. Metadata reads needed to prepare routing remain available. These checks do not infer all semantic goal changes or form a security boundary; hosted or special tools may bypass a host's hook path. Confirm hook execution and spawn rewriting on the active host before claiming enforcement there.

Private conversation state uses an OS temporary directory restricted to the current user. The default ignores plugin-only data variables so native hooks and agent-run `begin` share the same cache. An optional `JEV_CODEX_STATE_DIR` must be shared by both processes. State contains flags, digests, and minimal routing results; no API key, raw task text, or child brief is persisted. Jev receives only the sanitized routing request. Routing leaves global model defaults unchanged.

Sources: [Codex hooks](https://learn.chatgpt.com/docs/hooks), [plugin packaging](https://developers.openai.com/plugins/build/plugins).
