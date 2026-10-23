#!/usr/bin/env python3
"""Claude native combined-routing receipts: the agent begins, the mod claims."""

import contextlib
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import time

# Same private-state rules as the Codex gate; its hook logic is not used here.
from codex_gate import digest, file_lock, identifier, prepare_root, secure_open, unique_object
import route


MAX_BYTES = 131072
MAX_STATE_BYTES = 1048576
MAX_RECEIPTS = 256
TTL_SECONDS = 1800
PREFIX = "Jev routing: "
SKIP_REASONS = {"fixed_effort_unverified", "inventory_unavailable"}
# Input mistakes need a corrected request; only routing failures may fall back.
NO_RECEIPT = {"invalid_input", "invalid_arguments", "unsafe_input"}


class ReceiptError(Exception):
    def __init__(self, code, expected=None):
        self.code = code
        self.expected = expected


def require(condition, code="invalid_input"):
    if not condition:
        raise ReceiptError(code)


def state_root(state_dir):
    if state_dir is not None:
        return Path(state_dir)
    if os.environ.get("JEV_CLAUDE_STATE_DIR"):
        return Path(os.environ["JEV_CLAUDE_STATE_DIR"])
    return Path(tempfile.gettempdir()) / ("jev-claude-" + str(os.getuid()))


@contextlib.contextmanager
def session_state(session_id, state_dir):
    root = prepare_root(state_root(state_dir))
    stem = digest(session_id)
    with file_lock(root / (stem + ".lock"), 1):
        path = root / (stem + ".json")
        if path.exists() or path.is_symlink():
            with os.fdopen(secure_open(path, os.O_RDONLY), "rb") as source:
                raw = source.read(MAX_STATE_BYTES + 1)
            require(len(raw) <= MAX_STATE_BYTES, "invalid_state")
            state = json.loads(raw, object_pairs_hook=unique_object)
            require(isinstance(state, dict) and state.get("version") == 1
                    and isinstance(state.get("receipts"), dict), "invalid_state")
        else:
            state = {"version": 1, "receipts": {}}
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
        os.replace(temporary, path)


def optional_text(value, limit):
    return value is None or route.valid_text(value, limit)


def session_of(data):
    host_session = os.environ.get("CLAUDE_CODE_SESSION_ID") or None
    session_id = data.get("session_id", host_session)
    require(identifier(session_id))
    require(host_session is None or session_id == host_session, "session_mismatch")
    return session_id


def validate_begin(data):
    require(isinstance(data, dict)
            and set(data) <= {"session_id", "original", "request", "skip_subagent"})
    session_id = session_of(data)
    original = data.get("original")
    require(isinstance(original, dict) and set(original) == {"model", "effort"}
            and optional_text(original["model"], 256) and optional_text(original["effort"], 32))
    request = data.get("request")
    require(isinstance(request, dict))
    try:
        candidates = route.validate_input(request)
    except route.RoutingError as error:
        raise ReceiptError(error.code) from None
    require("skill" in candidates)
    if "subagent" in candidates:
        require("skip_subagent" not in data)
    else:
        require(data.get("skip_subagent") in SKIP_REASONS)
    key = os.environ.get("JEV_API_KEY")
    require(not key or not route.contains_secret(data, key), "unsafe_input")
    return session_id, candidates


def brief_line(receipt_id, model, effort, skills):
    return PREFIX + json.dumps({"receipt": receipt_id, "model": model, "effort": effort,
                                "skills": skills}, ensure_ascii=False, separators=(",", ":"))


def begin(data, state_dir=None):
    """Route one planned child and record a receipt for that one spawn."""
    session_id, candidates = validate_begin(data)
    original = data["original"]
    try:
        result = route.route(data["request"])
        decisions = result["decisions"]
        skills = decisions["skill"]["choices"]
        require(isinstance(skills, list) and set(skills) <= set(candidates["skill"]),
                "invalid_response")
        if "subagent" in candidates:
            chosen = candidates["subagent"].get(decisions["subagent"]["choice"])
            require(chosen is not None, "invalid_response")
            model, effort = chosen["model"], chosen["effort"]
        else:
            model, effort = original["model"], original["effort"]
        saved = {"status": "recommended", "router_model": result.get("router_model")}
    except (route.RoutingError, ReceiptError, KeyError, TypeError, AttributeError) as error:
        code = getattr(error, "code", "invalid_response")
        if code in NO_RECEIPT:
            raise ReceiptError(code) from None
        model, effort, skills = original["model"], original["effort"], []
        saved = {"status": "fallback", "code": code}
    receipt_id = "r-" + secrets.token_hex(8)
    now = int(time.time())
    saved.update({"created": now, "model": model, "effort": effort, "skills": skills,
                  "brief_line": brief_line(receipt_id, model, effort, skills), "claimed_by": None})
    if "skip_subagent" in data:
        saved["skip_subagent"] = data["skip_subagent"]
    with session_state(session_id, state_dir) as state:
        state["receipts"] = {key: value for key, value in state["receipts"].items()
                             if now - value["created"] <= TTL_SECONDS}
        require(len(state["receipts"]) < MAX_RECEIPTS, "state_full")
        state["receipts"][receipt_id] = saved
    output = {key: value for key, value in saved.items() if key not in {"created", "claimed_by"}}
    output["receipt_id"] = receipt_id
    if saved["status"] == "fallback":
        output["message"] = ("Jev routing failed; report it, use ordinary skills, and keep the "
                             "original spawn settings with this receipt.")
    return output


def validate_claim(data):
    require(isinstance(data, dict) and set(data) == {
        "session_id", "receipt_id", "spawn", "model", "effort", "brief_line"})
    require(identifier(data["session_id"]) and identifier(data["receipt_id"]))
    require(data["spawn"] is None or (isinstance(data["spawn"], str)
                                      and 0 < len(data["spawn"]) <= 1024))
    require(optional_text(data["model"], 256) and optional_text(data["effort"], 32))
    require(isinstance(data["brief_line"], str) and len(data["brief_line"]) <= 8192)


def claim(data, state_dir=None):
    """Bind one unused, fresh receipt to the spawn whose fields match it."""
    validate_claim(data)
    with session_state(data["session_id"], state_dir) as state:
        receipt = state["receipts"].get(data["receipt_id"])
        require(receipt is not None, "receipt_missing")
        require(int(time.time()) - receipt["created"] <= TTL_SECONDS, "receipt_expired")
        owner = None if data["spawn"] is None else digest(data["spawn"])
        require(receipt["claimed_by"] is None or (owner is not None and receipt["claimed_by"] == owner),
                "receipt_used")
        expected = {"model": receipt["model"], "effort": receipt["effort"],
                    "brief_line": receipt["brief_line"]}
        if data["brief_line"] != receipt["brief_line"]:
            raise ReceiptError("brief_mismatch", expected)
        if (data["model"], data["effort"]) != (receipt["model"], receipt["effort"]):
            raise ReceiptError("receipt_mismatch", expected)
        # An unkeyed spawn cannot repeat, so its claim is single-use.
        receipt["claimed_by"] = owner or "unkeyed-" + secrets.token_hex(8)
        keys = ("status", "code", "model", "effort", "skills", "skip_subagent")
        return {"status": "ok", "receipt": {key: receipt[key] for key in keys if key in receipt}}


HELP = """usage: claude_route.py begin|claim < JSON

begin (the agent, before each new non-fork Agent spawn while Claude native
skill and subagent routing are both on):
  session_id: the session ID from the Jev native context. Optional when
              CLAUDE_CODE_SESSION_ID is set; it must match that value.
  original: {model, effort} the spawn would use without Jev; null when unset.
  request: one route.py batch for this child, {host, task, decisions:
           {skill: eligible candidates ([] allowed), subagent?: verified
           {id, model, effort, description} options}, preference?}.
  skip_subagent: required exactly when request has no subagent decision:
           fixed_effort_unverified (the user fixed an effort that no matrix
           verifies) or inventory_unavailable (no model inventory).
  Output: status recommended or fallback, receipt_id, model, effort, skills,
  brief_line, and code/message for a fallback. Put brief_line verbatim on one
  line of the Agent prompt, set Agent.model to model and Agent.effort to
  effort (omit each when null), and load skills in the child. A routing
  failure (missing key, network, HTTP, invalid response) still writes a
  fallback receipt that keeps original settings and ordinary skills. Invalid
  or unsafe input writes no receipt and exits 1.

claim (the native mod at agent.spawn):
  {session_id, receipt_id, spawn: stable spawn key or null, model, effort,
   brief_line}. A receipt serves one spawn for 30 minutes; repeated events of
  the same keyed spawn reuse it. Errors: receipt_missing, receipt_expired,
  receipt_used, brief_mismatch and receipt_mismatch (with expected fields).

State is per-user private temporary storage keyed by a session digest:
model, effort, skill IDs, status, time and the brief line. No API key, task,
prompt, raw session ID or spawn ID is saved. JEV_CLAUDE_STATE_DIR overrides
the location only when both the agent shell and the mod see it.
"""


def main(argv=None):
    try:
        args = sys.argv[1:] if argv is None else argv
        if args == ["--help"]:
            print(HELP)
            return 0
        require(args in (["begin"], ["claim"]), "invalid_arguments")
        raw = sys.stdin.buffer.read(MAX_BYTES + 1)
        require(len(raw) <= MAX_BYTES)
        data = json.loads(raw, object_pairs_hook=unique_object)
        result = begin(data) if args == ["begin"] else claim(data)
    except ReceiptError as error:
        result = {"status": "error", "code": error.code}
        if error.expected is not None:
            result["expected"] = error.expected
    except Exception as error:
        code = getattr(error, "code", None)
        result = {"status": "error", "code": code if isinstance(code, str) else
                  "invalid_input" if isinstance(error, (ValueError, UnicodeError)) else "internal_error"}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return int(result["status"] == "error")


if __name__ == "__main__":
    sys.exit(main())
