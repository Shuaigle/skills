"""Public-boundary tests for opt-in Codex routing receipts."""

import copy
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import codex_gate as gate
import route


SECRET = "test-key-never-persist"
REAL_ROUTE = route.route


def hook(name, session="session-a", **fields):
    return {"hook_event_name": name, "session_id": session, **fields}


def unit(scopes=("task",), **fields):
    inventories = {
        "task": [{"id": "fast", "description": "Fast for a bounded task"},
                 {"id": "deep", "description": "Deeper reasoning"}],
        "skill": [{"id": "testing", "description": "Write behavioral tests"},
                  {"id": "docs", "description": "Write documentation"}],
        "subagent": [{"id": "child-fast", "description": "Fast child"},
                     {"id": "child-deep", "description": "Deep child"}],
    }
    result = {"session_id": "session-a", "turn_id": "turn-a", "unit_id": "read-config",
              "kind": "read", "target": "local", "request": {
                  "host": "codex", "task": "Read configuration and return a brief summary",
                  "decisions": {scope: inventories[scope] for scope in scopes}}}
    result.update(fields)
    return result


def recommendation(data):
    decisions = {}
    for scope, candidates in data["decisions"].items():
        if scope == "skill":
            decisions[scope] = {"choices": [item["id"] for item in candidates],
                                "evaluations": {}}
        else:
            decisions[scope] = {"choice": candidates[0]["id"], "confidence": 0.8,
                                "probabilities": {candidates[0]["id"]: 1.0}}
    return {"status": "recommended", "host": "codex", "router_model": "jev-test",
            "decisions": decisions}


class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {"JEV_API_KEY": SECRET})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.router = patch.object(route, "route", side_effect=recommendation).start()
        self.addCleanup(patch.stopall)

    def send(self, name, session="session-a", **fields):
        return gate.handle_hook(hook(name, session, **fields), self.tmp.name)

    def enable(self, scopes="task"):
        return self.send("UserPromptSubmit", prompt="jev on " + scopes, turn_id="control")

    def prompt(self, text="Read the configuration", turn="turn-a"):
        return self.send("UserPromptSubmit", prompt=text, turn_id=turn)

    def begin(self, data=None):
        return gate.begin_unit(unit() if data is None else data, self.tmp.name)

    def read(self, **fields):
        return self.send("PreToolUse", tool_name="Read",
                         tool_input={"file_path": "config.json"}, **fields)

    def test_only_anchored_human_control_enables_routing(self):
        for text in ('Please run jev on', '"jev on"', 'Example: jev on',
                     '```\njev on\n```', 'jev on imaginary'):
            self.prompt(text)
            self.assertEqual(self.read(), {})
        self.enable()
        self.prompt()
        denied = self.read()["hookSpecificOutput"]
        self.assertEqual(denied["permissionDecision"], "deny")
        self.assertIn("begin", denied["permissionDecisionReason"])
        self.router.assert_not_called()

    def test_first_receipt_routes_once_and_repeated_reads_reuse_it(self):
        self.enable()
        self.prompt()
        first = self.begin()
        second = self.begin()
        self.assertEqual(first["status"], "recommended")
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(first["decisions"]["task"]["choice"], "fast")
        self.assertEqual(first["task_model_application"], "pending_host_switch")
        self.assertEqual(self.read(), {})
        self.assertEqual(self.read(), {})
        self.router.assert_called_once()

    def test_independent_children_remain_prepared_and_route_in_parallel(self):
        self.enable("task subagent")
        self.prompt()
        self.begin(unit(unit_id="read-enabled"))
        barrier = threading.Barrier(2)
        def route_together(data):
            barrier.wait(timeout=3)
            return recommendation(data)
        self.router.side_effect = route_together
        children = []
        results = []
        for index in range(2):
            spawn = {"task_name": "child_" + str(index), "message": "Read one bounded module",
                     "fork_turns": "none", "model": "child-deep", "reasoning_effort": "high"}
            data = unit(("subagent",), target="subagent", unit_id="child-" + str(index),
                        spawn=spawn, efforts={"child-fast": ["low"]})
            children.append((spawn, data))
        def begin_child(data):
            try:
                results.append(self.begin(data))
            except Exception as error:
                results.append(error)
        threads = [threading.Thread(target=begin_child, args=(data,)) for _, data in children]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(isinstance(result, dict) for result in results), results)
        for spawn, _ in children:
            rewritten = self.send("PreToolUse", tool_name="spawn_agent", tool_input=spawn)
            output = rewritten["hookSpecificOutput"]
            self.assertEqual(output["permissionDecision"], "allow")
            self.assertEqual(output["updatedInput"], {**spawn, "model": "child-fast",
                                                     "reasoning_effort": "low"})
        self.assertEqual(self.read(), {})

    def test_concurrent_duplicate_begin_routes_once(self):
        self.enable()
        self.prompt()
        self.router.side_effect = lambda data: (time.sleep(0.1), recommendation(data))[1]
        results = []
        threads = [threading.Thread(target=lambda: results.append(self.begin())) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3)
        self.assertEqual(len(results), 4)
        self.assertEqual(sum(not result["cached"] for result in results), 1)
        self.router.assert_called_once()

    def test_disabled_session_isolation_and_lifecycle(self):
        self.prompt()
        data = unit(())
        self.assertEqual(self.begin(data)["status"], "disabled")
        self.router.assert_not_called()
        self.enable()
        self.prompt()
        self.begin(unit(unit_id="read-enabled"))
        self.assertEqual(self.send("PreToolUse", session="other-chat", tool_name="Read",
                                   tool_input={"file_path": "config.json"}), {})
        self.send("SessionStart", source="compact")
        self.assertEqual(self.read(), {})
        self.send("SessionStart", source="resume")
        self.assertEqual(self.read(), {})
        self.send("SessionStart", source="fork")
        self.assertEqual(self.read(), {})
        self.prompt()
        self.assertEqual(self.begin(unit(()))["status"], "disabled")

    def test_hook_only_plugin_data_does_not_split_the_state_store(self):
        with patch.object(gate.tempfile, "gettempdir", return_value=self.tmp.name):
            with patch.dict(os.environ, {"PLUGIN_DATA": self.tmp.name + "/plugin-only"}):
                gate.handle_hook(hook("UserPromptSubmit", prompt="jev on", turn_id="control"))
                gate.handle_hook(hook("UserPromptSubmit", prompt="Read a configuration", turn_id="turn-a"))
            with patch.dict(os.environ, {"PLUGIN_DATA": ""}):
                result = gate.begin_unit(unit())
        self.assertEqual(result["status"], "recommended")

    def test_missing_key_and_non_prompt_events_cannot_enable(self):
        with patch.dict(os.environ, {"JEV_API_KEY": ""}):
            output = self.enable()
        self.assertIn("missing_api_key", output["hookSpecificOutput"]["additionalContext"])
        self.send("PreToolUse", tool_name="Read", tool_input={"prompt": "jev on"})
        self.prompt()
        self.assertEqual(self.read(), {})
        with self.assertRaises(gate.GateError) as error:
            self.begin()
        self.assertEqual(error.exception.code, "decision_scope_mismatch")
        self.router.assert_not_called()

    def test_receipt_survives_continuation_but_scope_change_needs_new_id(self):
        self.enable()
        self.prompt()
        self.begin()
        self.prompt("Continue the same summary", turn="turn-b")
        continued = unit(turn_id="turn-b")
        self.assertTrue(self.begin(continued)["cached"])
        self.router.assert_called_once()
        changed = copy.deepcopy(continued)
        changed["request"]["task"] = "Read another independent configuration"
        with self.assertRaises(gate.GateError) as error:
            self.begin(changed)
        self.assertEqual(error.exception.code, "unit_conflict")
        changed["unit_id"] = "read-other-config"
        self.assertFalse(self.begin(changed)["cached"])
        self.assertEqual(self.router.call_count, 2)

    def test_read_to_edit_requires_new_receipt_and_stop_guard_terminates(self):
        self.enable()
        self.prompt()
        self.assertEqual(self.send("Stop")["decision"], "block")
        self.assertEqual(self.send("Stop", stop_hook_active=True), {})
        self.begin()
        self.assertEqual(self.send("Stop"), {})
        denied = self.send("PreToolUse", tool_name="apply_patch", tool_input={"patch": "..."})
        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")
        self.begin(unit(kind="edit", unit_id="edit-config"))
        self.assertEqual(self.send("PreToolUse", tool_name="apply_patch", tool_input={"patch": "..."}), {})
        self.send("UserPromptSubmit", prompt="jev status", turn_id="status")
        self.assertEqual(self.send("Stop"), {})

    def test_reading_and_parsing_same_batch_reuses_one_receipt(self):
        self.enable()
        self.prompt()
        self.begin()
        command = 'python3 -c \'import json; print(json.load(open("config.json")))\''
        self.assertEqual(self.send("PreToolUse", tool_name="Bash",
                                   tool_input={"command": command}), {})
        self.assertEqual(self.read(), {})
        self.router.assert_called_once()

    def test_declared_goal_can_read_supporting_files_without_new_routing(self):
        self.enable()
        self.prompt()
        for kind in ("edit", "verify", "research", "work"):
            with self.subTest(kind=kind):
                self.begin(unit(kind=kind, unit_id=kind + "-goal"))
                self.assertEqual(self.read(), {})
                self.assertEqual(self.send("PreToolUse", tool_name="Bash",
                                           tool_input={"command": "python3 inspect_result.py"}), {})
        self.assertEqual(self.router.call_count, 4)

    def test_read_and_research_still_require_new_unit_for_definite_writes_or_tests(self):
        self.enable()
        self.prompt()
        for kind in ("read", "research"):
            self.begin(unit(kind=kind, unit_id=kind + "-goal"))
            for name, arguments in (("apply_patch", {"patch": "..."}),
                                    ("Bash", {"command": "python3 -m unittest test_example.py"})):
                denied = self.send("PreToolUse", tool_name=name, tool_input=arguments)
                self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")
        self.begin(unit(kind="work", unit_id="mixed-goal"))
        self.assertEqual(self.send("PreToolUse", tool_name="apply_patch", tool_input={"patch": "..."}), {})
        self.assertEqual(self.send("PreToolUse", tool_name="Bash",
                                   tool_input={"command": "python3 -m unittest test_example.py"}), {})

    def test_skill_many_and_none_are_reused_without_probability_state(self):
        self.enable("skill")
        self.prompt()
        data = unit(("skill",))
        selected = self.begin(data)
        self.assertEqual(selected["decisions"]["skill"]["choices"], ["testing", "docs"])
        empty = unit(("skill",), unit_id="read-plain")
        empty["request"]["decisions"]["skill"] = []
        self.assertEqual(self.begin(empty)["decisions"]["skill"]["choices"], [])
        raw = "".join(path.read_text() for path in gate.Path(self.tmp.name).glob("*.json"))
        self.assertNotIn("probabilities", raw)
        self.assertNotIn("Read configuration", raw)
        self.assertNotIn(SECRET, raw)
        self.assertNotIn("session-a", raw)
        self.assertEqual(os.stat(self.tmp.name).st_mode & 0o777, 0o700)
        for path in gate.Path(self.tmp.name).iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_http_failure_is_visible_and_cached_for_unit(self):
        self.enable()
        self.prompt()
        self.router.side_effect = route.RoutingError("http_error")
        result = self.begin()
        self.assertEqual(result["status"], "fallback")
        self.assertEqual(result["code"], "http_error")
        self.assertIn("current model", result["message"])
        self.assertTrue(self.begin()["cached"])
        self.assertEqual(self.read(), {})
        self.router.assert_called_once()

    def test_unprepared_spawn_is_denied_even_with_model(self):
        self.enable("subagent")
        self.prompt()
        spawn = {"task_name": "reader", "message": "Summarize a module",
                 "fork_turns": "none", "model": "child-deep"}
        result = self.send("PreToolUse", tool_name="spawn_agent", tool_input=spawn)
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(self.read(), {})
        self.begin(unit(("subagent",), target="subagent", unit_id="child-reader", spawn=spawn))
        rewritten = self.send("PreToolUse", tool_name="spawn_agent", tool_input=spawn)
        self.assertEqual(rewritten["hookSpecificOutput"]["updatedInput"]["model"], "child-fast")
        self.prompt("Next task", turn="turn-b")
        self.assertEqual(self.send("PreToolUse", tool_name="spawn_agent", tool_input=spawn)
                         ["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_stale_turn_child_skip_and_missing_decision_domains(self):
        self.enable("task skill")
        self.prompt()
        self.assertEqual(self.read(turn_id="child-turn"), {})
        for data, code in ((unit(), "decision_scope_mismatch"),
                           (unit(("task", "skill"), turn_id="old-turn"), "stale_turn")):
            with self.assertRaises(gate.GateError) as error:
                self.begin(data)
            self.assertEqual(error.exception.code, code)
        self.router.assert_not_called()

    def test_only_exact_bootstrap_and_known_metadata_bypass_work_gate(self):
        self.enable()
        self.prompt()
        command = "python3 " + str(gate.SCRIPT) + " begin <<'JEV_UNIT'\n" + json.dumps(unit()) + "\nJEV_UNIT"
        self.assertEqual(self.send("PreToolUse", tool_name="Bash", tool_input={"command": command}), {})
        for bad in (command + "\ncat config.json", command.replace("JEV_UNIT'", "OTHER'", 1),
                    command.replace("<<'JEV_UNIT'", "<<JEV_UNIT"),
                    "python3 elsewhere.py begin <<'JEV_UNIT'\n{}\nJEV_UNIT"):
            result = self.send("PreToolUse", tool_name="Bash", tool_input={"command": bad})
            self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(self.send("PreToolUse", tool_name="Read", tool_input={"file_path": str(gate.SKILL / "SKILL.md")}), {})
        self.assertEqual(self.send("PreToolUse", tool_name="wait_agent", tool_input={}), {})

    def test_missing_fresh_context_is_rejected_before_routing(self):
        self.enable("subagent")
        self.prompt()
        spawn = {"task_name": "reader", "message": "Read a module"}
        for changed in (spawn, {**spawn, "fork_turns": "all"},
                        {**spawn, "fork_turns": "none", "fork_context": True}):
            with self.assertRaises(gate.GateError) as error:
                self.begin(unit(("subagent",), target="subagent", spawn=changed))
            self.assertEqual(error.exception.code, "fresh_context_required")
        self.router.assert_not_called()

    def test_invalid_router_choice_is_cached_as_fallback(self):
        self.enable()
        self.prompt()
        for index, choice in enumerate(("not-in-inventory", [], None)):
            result = recommendation(unit()["request"])
            result["decisions"]["task"]["choice"] = choice
            self.router.side_effect = None
            self.router.return_value = result
            data = unit(unit_id="bad-router-" + str(index))
            self.assertEqual(self.begin(data)["status"], "fallback")
            self.assertTrue(self.begin(data)["cached"])
        self.assertEqual(self.router.call_count, 3)

    def test_controls_support_explicit_invocations_and_independent_off(self):
        for prefix in ("jev", "$jev", "$shuaigle:jev", "/jev", "/shuaigle:jev"):
            self.send("UserPromptSubmit", prompt=prefix + " on all", turn_id="control")
            self.send("UserPromptSubmit", prompt=prefix + " off skill subagent", turn_id="control")
            self.prompt()
            self.begin(unit(unit_id="read-" + str(len(prefix))))
            self.send("UserPromptSubmit", prompt=prefix + " off", turn_id="control")
            self.assertEqual(self.read(), {})

    def test_hook_state_lock_busy_produces_denial_without_waiting_for_route(self):
        self.enable()
        self.prompt()
        with gate.locked_state("session-a", self.tmp.name):
            with patch.object(gate.time, "sleep"), patch.object(
                    gate.time, "monotonic", side_effect=(0, 2)):
                with self.assertRaises(gate.GateError) as error:
                    self.read()
        self.assertEqual(error.exception.code, "state_busy")

    def cli(self, args, raw):
        env = {**os.environ, "JEV_CODEX_STATE_DIR": self.tmp.name}
        return subprocess.run([sys.executable, str(gate.SCRIPT), *args], input=raw,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
                              timeout=5)

    def test_cli_help_bounded_json_duplicate_keys_and_redacted_errors(self):
        result = self.cli(["--help"], b"")
        self.assertEqual(result.returncode, 0)
        self.assertIn(b"unit_id", result.stdout)
        self.assertIn(b"pending_host_switch", result.stdout)
        for raw in (b'{"session_id":"a","session_id":"b"}',
                    b"x" * (gate.MAX_BYTES + 1), SECRET.encode(), b"{broken"):
            result = self.cli(["begin"], raw)
            self.assertEqual(result.returncode, 1)
            output = json.loads(result.stdout)
            self.assertEqual(output["status"], "error")
            self.assertNotIn(SECRET.encode(), result.stdout + result.stderr)
        malformed = json.dumps(hook("PreToolUse", tool_name="Read", tool_input=[])).encode()
        # A hook failure with recognizable PreToolUse input must deny visibly.
        self.enable()
        self.prompt()
        result = self.cli(["hook"], malformed)
        self.assertEqual(json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_receipt_reuse_reaches_real_router_http_boundary_once(self):
        self.enable("task skill")
        self.prompt()
        body = {"model": "jev-test", "answers": {
            "task": {"type": "choice", "choice": "fast", "confidence": 0.8,
                     "probabilities": {"fast": 0.8, "deep": 0.2}},
            "skill_0": {"type": "choice", "choice": "select", "confidence": 0.8,
                        "probabilities": {"select": 0.8, "skip": 0.2}},
            "skill_1": {"type": "choice", "choice": "skip", "confidence": 0.8,
                        "probabilities": {"select": 0.2, "skip": 0.8}}}}
        response = MagicMock(status=200)
        response.read.return_value = json.dumps(body).encode()
        self.router.side_effect = REAL_ROUTE
        with patch.object(route.http.client, "HTTPSConnection") as connection:
            connection.return_value.getresponse.return_value = response
            result = self.begin(unit(("task", "skill")))
            self.assertEqual(result["decisions"]["skill"]["choices"], ["testing"])
            self.begin(unit(("task", "skill")))
            self.read()
            self.read()
            connection.return_value.request.assert_called_once()
            payload = json.loads(connection.return_value.request.call_args.kwargs["body"])
            self.assertEqual(set(payload["questions"]), {"task", "skill_0", "skill_1"})
            self.assertNotIn("session-a", json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
