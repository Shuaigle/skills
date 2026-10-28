#!/usr/bin/env python3
"""Opt-in Codex hook gate and persistent, per-work-unit Jev receipts."""

import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sys
import tempfile
import time

import route


MAX_BYTES = 131072
MAX_STATE_BYTES = 4194304
MAX_UNITS = 2048
SCOPES = {"skill", "subagent"}
KINDS = {"read", "edit", "verify", "research", "work"}
SCRIPT = Path(__file__).resolve()
SKILL = SCRIPT.parent.parent
UNIT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}\Z")
CONTROL_RE = re.compile(r"(?:jev|\$jev|\$shuaigle:jev|/jev|/shuaigle:jev)(?:[ \t]+(.*))?\Z")


class GateError(Exception):
    def __init__(self, code):
        self.code = code


def require(condition, code="invalid_input"):
    if not condition:
        raise GateError(code)


def digest(value):
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False,
                         allow_nan=False, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def unique_object(pairs):
    result = {}
    for name, value in pairs:
        require(name not in result)
        result[name] = value
    return result


def identifier(value):
    return isinstance(value, str) and 0 < len(value) <= 256 and not any(
        ord(char) < 32 for char in value)


def blank_state():
    return {"version": 3, "enabled": [], "turn": None,
            "pending": False, "active": None, "prepared": {}, "units": {}}


def state_root(state_dir):
    if state_dir is not None:
        return Path(state_dir)
    if os.environ.get("JEV_CODEX_STATE_DIR"):
        return Path(os.environ["JEV_CODEX_STATE_DIR"])
    # PLUGIN_DATA exists only in hook commands, not ordinary begin invocations.
    return Path(tempfile.gettempdir()) / ("jev-codex-" + str(os.getuid()))


def secure_open(path, flags):
    fd = os.open(str(path), flags | getattr(os, "O_NOFOLLOW", 0), 0o600)
    os.fchmod(fd, 0o600)
    return fd


def prepare_root(state_dir):
    root = state_root(state_dir)
    require(not root.is_symlink(), "unsafe_state")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(root.is_dir() and root.stat().st_uid == os.getuid(), "unsafe_state")
    root.chmod(0o700)
    return root


@contextlib.contextmanager
def file_lock(path, timeout):
    lock_fd = secure_open(path, os.O_CREAT | os.O_RDWR)
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                require(time.monotonic() < deadline, "state_busy")
                time.sleep(0.01)
        yield
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


@contextlib.contextmanager
def locked_state(session_id, state_dir=None):
    require(identifier(session_id))
    root = prepare_root(state_dir)
    stem = digest(session_id)
    with file_lock(root / (stem + ".lock"), 1):
        state_path = root / (stem + ".json")
        if state_path.exists() or state_path.is_symlink():
            with os.fdopen(secure_open(state_path, os.O_RDONLY), "rb") as source:
                raw = source.read(MAX_STATE_BYTES + 1)
            require(len(raw) <= MAX_STATE_BYTES, "invalid_state")
            state = json.loads(raw, object_pairs_hook=unique_object)
            require(isinstance(state, dict) and state.get("version") in {1, 2, 3}
                    and isinstance(state.get("units"), dict)
                    and isinstance(state.get("enabled"), list)
                    and set(state["enabled"]) <= (SCOPES | {"task"}
                         if state["version"] == 1 else SCOPES), "invalid_state")
            if state["version"] < 3:
                # Preserve existing human authorization, never resurrect the
                # retired task scope or interpret old model IDs as option IDs.
                enabled = sorted(set(state["enabled"]) & SCOPES)
                state = blank_state()
                state["enabled"] = enabled
        else:
            state = blank_state()
        yield state
        raw = json.dumps(state, ensure_ascii=False, allow_nan=False,
                         separators=(",", ":")).encode()
        require(len(raw) <= MAX_STATE_BYTES, "state_full")
        fd, temporary = tempfile.mkstemp(prefix=stem + ".", suffix=".tmp", dir=str(root))
        with os.fdopen(fd, "wb") as destination:
            os.fchmod(destination.fileno(), 0o600)
            destination.write(raw)
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary, state_path)


def flags_root(state_dir):
    # Saved flags outlive sessions; hook-only PLUGIN_DATA keeps them clear of temp-directory cleanup.
    if state_dir is None and not os.environ.get("JEV_CODEX_STATE_DIR") and os.environ.get("PLUGIN_DATA"):
        return prepare_root(os.environ["PLUGIN_DATA"])
    return prepare_root(state_dir)


def saved_flags(state_dir):
    """Returns the last human-set scopes, or None when nothing readable was saved."""
    try:
        with os.fdopen(secure_open(flags_root(state_dir) / "flags.json", os.O_RDONLY), "rb") as source:
            data = json.loads(source.read(4096))
    except (OSError, ValueError, GateError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("enabled"), list):
        return None
    return sorted({scope for scope in data["enabled"] if isinstance(scope, str) and scope in SCOPES})


def save_flags(enabled, state_dir):
    root = flags_root(state_dir)
    fd, temporary = tempfile.mkstemp(prefix="flags.", suffix=".tmp", dir=str(root))
    with os.fdopen(fd, "wb") as destination:
        destination.write(json.dumps({"enabled": enabled}).encode())
        destination.flush()
        os.fsync(destination.fileno())
    os.replace(temporary, root / "flags.json")


def context(event_name, message):
    return {"hookSpecificOutput": {"hookEventName": event_name,
                                   "additionalContext": message}}


def deny(message):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "deny",
                                   "permissionDecisionReason": message}}


def control(first_line):
    match = CONTROL_RE.fullmatch(first_line)
    if not match:
        return None
    words = (match.group(1) or "status").split()
    if not words or words[0] not in {"on", "off", "status"}:
        return ("invalid", set())
    action = words[0]
    if action == "status":
        return (action if len(words) == 1 else "invalid", set())
    arguments = words[1:]
    if not arguments:
        scopes = set(SCOPES)
    elif arguments == ["all"]:
        scopes = set(SCOPES)
    elif set(arguments) <= SCOPES:
        scopes = set(arguments)
    else:
        return ("invalid", set())
    return action, scopes


def turn_matches(value, state):
    return isinstance(value, str) and (value == state["turn"] or digest(value) == state["turn"])


def bootstrap_context(event, state, warning=None):
    receipt = {"session_id": event["session_id"], "turn_id": state["turn"],
               "enabled": state["enabled"]}
    message = "Jev routing " + json.dumps(receipt, separators=(",", ":"))
    if warning:
        message += ". " + warning
    if state["pending"] and state["enabled"]:
        message += (". Before each independent work unit, call python3 "
                    + shlex.quote(str(SCRIPT))
                    + " begin with a JSON stdin receipt. Reuse that unit's decisions for its"
                    " batch and continuations; declare a new unit when scope changes."
                    " Read the Jev Codex hook instructions for the input contract.")
    return context("UserPromptSubmit", message)


def handle_hook(event, state_dir=None):
    """Consume a trusted host hook event; only UserPromptSubmit may change flags."""
    require(isinstance(event, dict) and identifier(event.get("session_id")))
    name = event.get("hook_event_name")
    require(name in {"SessionStart", "SessionEnd", "UserPromptSubmit", "PreToolUse", "Stop"})
    with locked_state(event["session_id"], state_dir) as state:
        if name == "SessionStart":
            if event.get("source", "startup") not in {"resume", "compact"}:
                state.clear()
                state.update(blank_state())
            # The last human control holds across conversations; without a key saved flags stay off.
            saved = saved_flags(state_dir)
            if saved is not None and route.valid_text(os.environ.get("JEV_API_KEY"), 4096):
                state["enabled"] = saved
            return {}
        if name == "SessionEnd":
            state.clear()
            state.update(blank_state())
            return {}
        if name == "UserPromptSubmit":
            prompt = event.get("prompt")
            require(isinstance(prompt, str) and len(prompt.encode()) <= MAX_BYTES)
            lines = prompt.splitlines()
            selected = control(lines[0]) if lines else None
            state["turn"] = digest(event.get("turn_id") or os.urandom(24).hex())
            state["active"] = None
            state["prepared"] = {}
            state["pending"] = bool(prompt.strip()) if selected is None else bool("\n".join(lines[1:]).strip())
            warning = None
            if selected:
                action, scopes = selected
                if action == "invalid":
                    warning = "Invalid control; flags unchanged."
                elif action == "on" and not route.valid_text(os.environ.get("JEV_API_KEY"), 4096):
                    warning = "missing_api_key; flags unchanged."
                elif action == "on":
                    state["enabled"] = sorted(set(state["enabled"]) | scopes)
                elif action == "off":
                    state["enabled"] = sorted(set(state["enabled"]) - scopes)
                if action in {"on", "off"} and warning is None:
                    try:
                        save_flags(state["enabled"], state_dir)
                    except (OSError, GateError):
                        warning = "flags_not_saved; the change applies to this conversation only."
                return bootstrap_context(event, state, warning)
            return bootstrap_context(event, state) if state["enabled"] else {}
        if not state["enabled"]:
            return {}
        if event.get("turn_id") is not None and not turn_matches(event["turn_id"], state):
            return {}
        if name == "Stop":
            if (state["pending"] and "skill" in state["enabled"]
                    and state["active"] is None and not event.get("stop_hook_active")):
                return {"decision": "block", "reason":
                        "Jev is enabled: declare and route the pending work with codex_gate.py begin before finishing."}
            return {}
        return pre_tool(event, state)


def validate_begin(data):
    require(isinstance(data, dict) and set(data) <= {
        "session_id", "turn_id", "unit_id", "kind", "target", "request", "spawn", "efforts"})
    require(identifier(data.get("session_id")) and identifier(data.get("turn_id")))
    require(isinstance(data.get("unit_id"), str) and UNIT_RE.fullmatch(data["unit_id"]))
    require(data.get("kind") in KINDS and data.get("target") in {"local", "subagent"})
    request = data.get("request")
    require(isinstance(request, dict) and "decisions" in request and "models" not in request)
    try:
        candidates = route.validate_input(request)
    except route.RoutingError as error:
        raise GateError(error.code) from None
    require(request["host"].lower() == "codex")
    if data["target"] == "subagent":
        validate_spawn(data.get("spawn"))
    else:
        require("spawn" not in data)
    efforts = data.get("efforts", {})
    require(isinstance(efforts, dict) and len(efforts) <= 255)
    for model, values in efforts.items():
        require(route.valid_text(model, 256))
        require(isinstance(values, list) and all(route.valid_text(item, 32) for item in values)
                and len(values) <= 16 and len(set(values)) == len(values))
    for option in candidates.get("subagent", {}).values():
        require(option["model"] in efforts)
        supported = efforts[option["model"]]
        require(option["effort"] in supported if supported else option["effort"] is None)
    key = os.environ.get("JEV_API_KEY")
    require(not key or not route.contains_secret(data, key), "unsafe_input")
    require(len(json.dumps(data, ensure_ascii=False, allow_nan=False).encode()) <= MAX_BYTES)
    return candidates


def validate_spawn(spawn):
    require(isinstance(spawn, dict) and isinstance(spawn.get("message", spawn.get("prompt")), str))
    require(spawn.get("fork_turns", "none") == "none" and not spawn.get("fork_context", False),
            "fresh_context_required")
    # Codex spawn_agent inherits all turns when fork_turns is omitted.
    require("task_name" not in spawn or spawn.get("fork_turns") == "none", "fresh_context_required")


def spawn_fingerprint(spawn):
    return digest({key: value for key, value in spawn.items()
                   if key not in {"model", "reasoning_effort"}})


def minimal_result(result, candidates):
    """Defensively bind the router result to the supplied decision inventory."""
    require(isinstance(result, dict) and result.get("status") == "recommended", "invalid_response")
    answers = result.get("decisions")
    require(isinstance(answers, dict) and set(answers) == set(candidates), "invalid_response")
    saved = {}
    for scope, inventory in candidates.items():
        answer = answers[scope]
        require(isinstance(answer, dict), "invalid_response")
        if scope == "skill":
            choices = answer.get("choices")
            require(isinstance(choices, list) and all(isinstance(item, str) for item in choices)
                    and len(set(choices)) == len(choices) and set(choices) <= set(inventory),
                    "invalid_response")
            saved[scope] = {"choices": choices}
        else:
            require(isinstance(answer.get("choice"), str) and answer["choice"] in inventory
                    and route.probability(answer.get("confidence")),
                    "invalid_response")
            option = inventory[answer["choice"]]
            require(answer.get("model") == option["model"] and "effort" in answer
                    and answer["effort"] == option["effort"], "invalid_response")
            saved[scope] = {"choice": answer["choice"], "model": option["model"],
                            "effort": option["effort"], "confidence": answer["confidence"]}
    router_model = result.get("router_model")
    require(router_model is None or isinstance(router_model, str)
            and re.fullmatch(r"jev-[A-Za-z0-9._-]{1,64}", router_model), "invalid_response")
    return {"status": "recommended", "decisions": saved, "router_model": router_model}


def begin_unit(data, state_dir=None):
    """Route an immutable work unit once, without changing human-controlled flags."""
    candidates = validate_begin(data)
    unit_key = digest(data["unit_id"])
    lock_path = prepare_root(state_dir) / (digest(data["session_id"]) + "-" + unit_key + ".lock")
    # Distinct units route concurrently; only duplicate work waits for its receipt.
    with file_lock(lock_path, route.TIMEOUT + 2):
        with locked_state(data["session_id"], state_dir) as state:
            require(turn_matches(data["turn_id"], state), "stale_turn")
            applicable = {"skill"} if data["target"] == "local" else SCOPES
            enabled = set(state["enabled"]) & applicable
            require(set(candidates) == enabled, "decision_scope_mismatch")
            fingerprint_data = {"request": data["request"], "kind": data["kind"],
                                "target": data["target"], "enabled": sorted(enabled),
                                "efforts": data.get("efforts", {})}
            if data["target"] == "subagent":
                fingerprint_data["spawn"] = spawn_fingerprint(data["spawn"])
            fingerprint = digest(fingerprint_data)
            existing = state["units"].get(unit_key)
            if existing is not None:
                require(existing["fingerprint"] == fingerprint, "unit_conflict")
                receipt = existing
                cached = True
            else:
                require(len(state["units"]) < MAX_UNITS, "state_full")
                cached = False
        if not cached:
            try:
                if not enabled:
                    result = {"status": "disabled", "decisions": {}}
                else:
                    result = minimal_result(route.route(data["request"]), candidates)
            except (route.RoutingError, GateError) as error:
                result = {"status": "fallback", "code": error.code, "decisions": {}}
            receipt = {"fingerprint": fingerprint, "kind": data["kind"], "target": data["target"],
                       "enabled": sorted(enabled), "result": result}
            if data["target"] == "subagent":
                receipt["spawn"] = spawn_fingerprint(data["spawn"])
        with locked_state(data["session_id"], state_dir) as state:
            require(turn_matches(data["turn_id"], state), "stale_turn")
            require(set(state["enabled"]) & applicable == enabled, "decision_scope_mismatch")
            require(unit_key in state["units"] or len(state["units"]) < MAX_UNITS, "state_full")
            state["units"][unit_key] = receipt
            if data["target"] == "local":
                state["active"] = unit_key
            else:
                state["prepared"][receipt["spawn"]] = unit_key
            result = {**receipt["result"], "unit_id": data["unit_id"], "cached": cached}
            if result["status"] == "fallback":
                result["message"] = (
                    "Jev routing failed; use the ordinary skill workflow and inherited child model for this unit.")
            return result


def tool_details(event):
    name = event.get("tool_name")
    arguments = event.get("tool_input", {})
    require(isinstance(name, str) and isinstance(arguments, dict))
    name = name.split(".")[-1].split("__")[-1].lower()
    return name, arguments


def shell_command(arguments):
    return arguments.get("command", arguments.get("cmd", ""))


def is_bootstrap(command):
    if not isinstance(command, str) or len(command.encode()) > MAX_BYTES:
        return False
    lines = command.splitlines()
    if (len(lines) < 3 or lines[-1] != "JEV_UNIT"
            or not lines[0].endswith(" <<'JEV_UNIT'")):
        return False
    try:
        words = shlex.split(lines[0])
        if words != ["python3", str(SCRIPT), "begin", "<<JEV_UNIT"]:
            return False
        json.loads("\n".join(lines[1:-1]), object_pairs_hook=unique_object)
    except (ValueError, GateError):
        return False
    return True


def metadata_path(value):
    if not isinstance(value, str):
        return False
    path = Path(value).expanduser().resolve()
    allowed = {SKILL / "SKILL.md", SKILL / "agents" / "openai.yaml", SCRIPT,
               SCRIPT.parent / "route.py"}
    allowed.update((SKILL / "references").glob("*.md"))
    allowed.add(Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser() / "models_cache.json")
    return path in allowed


def is_metadata_read(name, arguments):
    if name in {"read", "read_file"}:
        return metadata_path(arguments.get("file_path", arguments.get("path")))
    if name in {"bash", "exec_command"}:
        try:
            words = shlex.split(shell_command(arguments))
        except (ValueError, TypeError):
            return False
        if words[:1] == ["cat"] and len(words) == 2:
            return metadata_path(words[1])
        if words == ["python3", str(SCRIPT), "--help"]:
            return True
    return False


def work_kind(name, arguments):
    if name in {"read", "read_file", "glob", "grep", "list_dir", "list_directory"}:
        return "read"
    if name in {"apply_patch", "edit", "write", "write_file", "multiedit"}:
        return "edit"
    if name in {"bash", "exec_command"}:
        command = shell_command(arguments)
        if not isinstance(command, str):
            return "work"
        try:
            words = shlex.split(command)
        except ValueError:
            return "work"
        if words and words[0] in {"cat", "rg", "sed", "ls", "head", "tail", "find", "pwd", "wc"}:
            return "read"
        if re.search(r"(?:^|\s)(?:pytest|unittest|test|check|validate)(?:\s|[._:]|$)", command):
            return "verify"
        return "work"
    if any(part in name for part in ("search", "browse", "fetch", "retrieve")):
        return "research"
    return "work"


def pre_tool(event, state):
    name, arguments = tool_details(event)
    if name in {"wait", "wait_agent", "list_agents", "wait_threads"}:
        return {}
    if name in {"bash", "exec_command"} and is_bootstrap(shell_command(arguments)):
        return {}
    if is_metadata_read(name, arguments):
        return {}
    enabled = set(state["enabled"])
    if name in {"spawn_agent", "agent"}:
        if not enabled & {"subagent", "skill"}:
            return {}
        receipt_key = state["prepared"].get(spawn_fingerprint(arguments))
        receipt = state["units"].get(receipt_key, {})
        if receipt.get("target") != "subagent" or receipt.get("spawn") != spawn_fingerprint(arguments):
            return deny("Jev requires a prepared child unit matching this spawn; call codex_gate.py begin first.")
        result = receipt["result"]
        if result["status"] != "recommended" or "subagent" not in result["decisions"]:
            return {}
        selected = result["decisions"]["subagent"]
        updated = {**arguments, "model": selected["model"]}
        if selected["effort"] is None:
            updated.pop("reasoning_effort", None)
        else:
            updated["reasoning_effort"] = selected["effort"]
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                       "permissionDecision": "allow", "updatedInput": updated}}
    if "skill" not in enabled:
        return {}
    receipt = state["units"].get(state["active"], {})
    if receipt.get("target") != "local":
        return deny("Jev is enabled: declare this independent work unit with codex_gate.py begin before using work tools.")
    kind = work_kind(name, arguments)
    # Tools do not reveal semantic task boundaries. A goal can read supporting
    # files or run an unclassified parser without becoming independent work.
    if receipt["kind"] != kind and kind not in {"read", "work"} and receipt["kind"] != "work":
        return deny("Jev work kind changed; begin a new unit or reactivate a matching cached unit before continuing.")
    return {}


HELP = """usage: codex_gate.py hook|begin < JSON

hook accepts trusted Codex SessionStart, SessionEnd, UserPromptSubmit,
PreToolUse and Stop events. Only an anchored first-line human jev control in
UserPromptSubmit changes skill/subagent flags. The last on/off control is saved
and restored at every conversation start while JEV_API_KEY is set.
Bare jev on and jev on all enable both. The retired task control is invalid.

begin fields:
  session_id, turn_id: echo the host context; turn_id may be its emitted token.
  unit_id: stable 1-80 ASCII letters/digits/dot/underscore/hyphen identifier.
  kind: read | edit | verify | research | work. Supporting reads and unknown
        tool kinds reuse the declared unit. work explicitly permits mixed
        tools; definite edits/tests outside compatible units need a new unit.
  target: local | subagent.
  request: route.py batch {host: "codex", task: sanitized summary,
           decisions: {skill?: eligible candidates,
                       subagent?: live model-effort option candidates},
           preference?: string}.
           Include exactly the enabled applicable domains: local skill,
           or child subagent/skill. Skill candidates are {id, description}.
           Each child option is exactly {id: opaque option ID, model: host ID,
           effort: supported effort string or null, description: capability}.
  spawn: exact planned child tool arguments, required only for subagent;
         Codex spawn_agent requires fork_turns: "none" and a self-contained
         message. Model and reasoning_effort are rebound by PreToolUse.
  efforts: authoritative live {child_model_id: [supported reasoning efforts]}.
           Required for subagent decisions; cover every candidate model.
           A nonempty list permits only its efforts. [] permits only null,
           meaning default-only/no per-spawn effort control. At most 255
           models and 16 unique effort strings per model; other host models
           may be present. Unsupported/missing pairs fail before routing.

The same unit_id and immutable input reuse one routing receipt across tools,
continuations and concurrent duplicate begins. Changed work or inventories
require a new unit_id. Different units may route concurrently. Failed routing
is a visible cached fallback to the inherited child model and ordinary
skills; repeated tools do not retry Jev. Skill choices can contain zero or
multiple IDs. Jev selects each child's model and effort atomically in that
same request. The exact pair is applied; null removes an effort override.
The main model stays unchanged; routing selects optional skills and model-
effort pairs only for planned fresh-context children.

Bootstrap work gate with exactly:
  python3 <absolute installed codex_gate.py> begin <<'JEV_UNIT'
  <begin JSON>
  JEV_UNIT
No extra shell commands. Metadata reads and coordination waits are exempt.
The host must load hooks and emit supported events for enforcement. Each unit
retains minimal choices in private per-user temporary state; no raw task,
prompt, probabilities or API key is saved. JEV_CODEX_STATE_DIR overrides the
shared default only when present in both hook and begin environments.
"""


def main(argv=None):
    data = None
    try:
        args = sys.argv[1:] if argv is None else argv
        if args == ["--help"]:
            print(HELP)
            return 0
        require(args in (["hook"], ["begin"]), "invalid_arguments")
        raw = sys.stdin.buffer.read(MAX_BYTES + 1)
        require(len(raw) <= MAX_BYTES)
        data = json.loads(raw, object_pairs_hook=unique_object)
        result = handle_hook(data) if args == ["hook"] else begin_unit(data)
    except (GateError, route.RoutingError) as error:
        result = {"status": "error", "code": error.code}
    except (ValueError, UnicodeError):
        result = {"status": "error", "code": "invalid_input"}
    except Exception:
        result = {"status": "error", "code": "internal_error"}
    if (result.get("status") == "error" and isinstance(data, dict)
            and data.get("hook_event_name") == "PreToolUse"):
        result = deny("Jev hook failed (" + result["code"]
                      + "); retry after correcting the hook state or explicitly disable Jev.")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return int(result.get("status") == "error")


if __name__ == "__main__":
    sys.exit(main())
