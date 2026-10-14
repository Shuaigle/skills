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


def unit(scopes=("skill",), **fields):
    inventories = {
        "skill": [{"id": "testing", "description": "Write behavioral tests"},
                  {"id": "docs", "description": "Write documentation"}],
        "subagent": [{"id": "fast-low", "model": "child-fast", "effort": "low",
                      "description": "Fast child with low reasoning"},
                     {"id": "deep-high", "model": "child-deep", "effort": "high",
                      "description": "Deep child with high reasoning"}],
    }
    result = {"session_id": "session-a", "turn_id": "turn-a", "unit_id": "read-config",
              "kind": "read", "target": "local", "request": {
                  "host": "codex", "task": "Read configuration and return a brief summary",
                  "decisions": {scope: inventories[scope] for scope in scopes}}}
    if "subagent" in scopes:
        result["efforts"] = {"child-fast": ["low", "medium"], "child-deep": ["high"]}
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
                                "model": candidates[0]["model"], "effort": candidates[0]["effort"],
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

    def enable(self, scopes="skill"):
        return self.send("UserPromptSubmit", prompt="jev on " + scopes, turn_id="control")

    def prompt(self, text="Read the configuration", turn="turn-a"):
        return self.send("UserPromptSubmit", prompt=text, turn_id=turn)

    def begin(self, data=None):
        return gate.begin_unit(unit() if data is None else data, self.tmp.name)

    def read(self, **fields):
        return self.send("PreToolUse", tool_name="Read",
                         tool_input={"file_path": "config.json"}, **fields)

    def test_bare_on_and_all_enable_only_skill_and_subagent(self):
        for command in ("jev on", "jev on all"):
            with self.subTest(command=command):
                self.send("SessionStart", source="startup")
                self.send("UserPromptSubmit", prompt=command, turn_id="control")
                self.prompt()
                self.begin(unit(("skill",)))
                spawn = {"task_name": "reader", "message": "Summarize a bounded module",
                         "fork_turns": "none"}
                self.begin(unit(("skill", "subagent"), target="subagent", unit_id="child-reader",
                                spawn=spawn))
                result = self.send("UserPromptSubmit", prompt="jev status", turn_id="status")
                context = result["hookSpecificOutput"]["additionalContext"]
                self.assertIn('"enabled":["skill","subagent"]', context)
                self.assertNotIn('"task"', context)

    def test_task_controls_are_invalid_and_leave_flags_unchanged(self):
        self.enable("skill")
        for command in ("jev on task", "jev off task", "jev on task subagent"):
            result = self.send("UserPromptSubmit", prompt=command, turn_id="control")
            context = result["hookSpecificOutput"]["additionalContext"]
            self.assertIn("Invalid control", context)
            self.assertIn('"enabled":["skill"]', context)
        self.router.assert_not_called()

    def test_legacy_main_model_requests_fail_before_route_instead_of_fallback(self):
        self.enable("skill")
        self.prompt()
        values = [unit(("skill",)) for _ in range(3)]
        values[0]["request"]["current_model"] = "fast"
        values[1]["request"]["models"] = [{"id": "fast", "description": "Fast model"}]
        values[2]["request"]["decisions"]["task"] = [{"id": "fast", "description": "Fast model"}]
        for data in values:
            with self.assertRaises(gate.GateError) as error:
                self.begin(data)
            self.assertEqual(error.exception.code, "invalid_input")
        self.router.assert_not_called()

    def test_v1_state_preserves_only_previously_authorized_current_scopes(self):
        path = gate.Path(self.tmp.name) / (gate.digest("session-a") + ".json")
        for enabled, expected in ((["task"], []), (["task", "skill"], ["skill"]),
                                  (["task", "skill", "subagent"], ["skill", "subagent"])):
            previous = {"version": 1, "enabled": enabled, "turn": "old-turn",
                        "pending": True, "active": "old-unit", "prepared": {"old-spawn": "old-unit"},
                        "units": {"old-unit": {"result": {"decisions": {"task": {"choice": "fast"}}}}}}
            path.write_text(json.dumps(previous))
            self.send("SessionStart", source="resume")
            current = json.loads(path.read_text())
            self.assertEqual(current["version"], 3)
            self.assertEqual(current["enabled"], expected)
            self.assertEqual(current["units"], {})
            self.assertEqual(current["prepared"], {})
            self.assertIsNone(current["active"])
            self.assertNotIn('"task"', path.read_text())
        self.router.assert_not_called()

    def test_child_decision_combinations_leave_the_main_model_untouched(self):
        spawn = {"task_name": "reader", "message": "Summarize a bounded module",
                 "fork_turns": "none", "model": "child-deep"}
        for scopes in (("skill",), ("subagent",), ("skill", "subagent")):
            with self.subTest(scopes=scopes):
                self.send("SessionStart", source="startup")
                self.enable(" ".join(scopes))
                self.prompt()
                local = unit(("skill",) if "skill" in scopes else ())
                self.begin(local)
                self.assertEqual(self.read(), {})
                data = unit(scopes, target="subagent", unit_id="child-reader", spawn=spawn)
                before = self.router.call_count
                result = self.begin(data)
                self.assertEqual(set(result["decisions"]), set(scopes))
                self.assertNotIn("task_model_application", result)
                self.assertNotIn("model", result)
                self.assertTrue(self.begin(data)["cached"])
                self.assertEqual(self.router.call_count, before + 1)
                rewritten = self.send("PreToolUse", tool_name="spawn_agent", tool_input=spawn)
                if "subagent" in scopes:
                    updated = rewritten["hookSpecificOutput"]["updatedInput"]
                    self.assertEqual(updated, {**spawn, "model": "child-fast", "reasoning_effort": "low"})
                else:
                    self.assertEqual(rewritten, {})
                self.assertEqual(self.read(), {})

    def test_child_pair_must_belong_to_authoritative_live_matrix_before_route(self):
        self.enable("subagent")
        self.prompt()
        spawn = {"task_name": "reader", "message": "Summarize a module", "fork_turns": "none"}
        original = unit(("subagent",), target="subagent", spawn=spawn)
        cases = []
        missing = copy.deepcopy(original)
        missing.pop("efforts")
        cases.append(missing)
        uncovered = copy.deepcopy(original)
        uncovered["efforts"].pop("child-deep")
        cases.append(uncovered)
        unsupported = copy.deepcopy(original)
        unsupported["request"]["decisions"]["subagent"][0]["effort"] = "ultra"
        cases.append(unsupported)
        no_control = copy.deepcopy(original)
        no_control["efforts"]["child-fast"] = []
        cases.append(no_control)
        invalid_default = copy.deepcopy(original)
        invalid_default["request"]["decisions"]["subagent"][0]["effort"] = None
        cases.append(invalid_default)
        for data in cases:
            with self.subTest(data=data), self.assertRaises(gate.GateError) as error:
                self.begin(data)
            self.assertEqual(error.exception.code, "invalid_input")
        self.router.assert_not_called()

    def test_selected_exact_effort_is_applied_and_null_omits_override(self):
        self.enable("subagent")
        self.prompt()
        spawn = {"task_name": "reader", "message": "Summarize a module", "fork_turns": "none",
                 "model": "child-deep", "reasoning_effort": "high"}
        data = unit(("subagent",), target="subagent", spawn=spawn)
        # Medium is legal but is not the first effort in the host matrix.
        data["request"]["decisions"]["subagent"][0]["effort"] = "medium"
        result = self.begin(data)
        self.assertEqual(result["decisions"]["subagent"]["choice"], "fast-low")
        self.assertEqual(result["decisions"]["subagent"]["model"], "child-fast")
        self.assertEqual(result["decisions"]["subagent"]["effort"], "medium")
        updated = self.send("PreToolUse", tool_name="spawn_agent", tool_input=spawn)
        self.assertEqual(updated["hookSpecificOutput"]["updatedInput"],
                         {**spawn, "model": "child-fast", "reasoning_effort": "medium"})
        null_data = copy.deepcopy(data)
        null_data["unit_id"] = "default-only-child"
        null_data["efforts"]["child-fast"] = []
        null_data["request"]["decisions"]["subagent"][0]["effort"] = None
        self.begin(null_data)
        updated = self.send("PreToolUse", tool_name="spawn_agent", tool_input=spawn)
        expected = {**spawn, "model": "child-fast"}
        expected.pop("reasoning_effort")
        self.assertEqual(updated["hookSpecificOutput"]["updatedInput"], expected)

    def test_router_cannot_return_a_model_effort_pair_other_than_selected_option(self):
        self.enable("subagent")
        self.prompt()
        spawn = {"task_name": "reader", "message": "Summarize a module", "fork_turns": "none"}
        for index, changed in enumerate(({"model": "child-deep"}, {"effort": "medium"},
                                         {"effort": None})):
            data = unit(("subagent",), target="subagent", spawn=spawn,
                        unit_id="mismatched-pair-" + str(index))
            result = recommendation(data["request"])
            result["decisions"]["subagent"].update(changed)
            self.router.side_effect = None
            self.router.return_value = result
            self.assertEqual(self.begin(data)["status"], "fallback")
            self.assertTrue(self.begin(data)["cached"])
            self.assertEqual(self.send("PreToolUse", tool_name="spawn_agent", tool_input=spawn), {})
        self.assertEqual(self.router.call_count, 3)

    def test_v2_cached_model_choice_is_not_reused_as_an_atomic_option(self):
        path = gate.Path(self.tmp.name) / (gate.digest("session-a") + ".json")
        previous = {"version": 2, "enabled": ["skill", "subagent"], "turn": "old-turn",
                    "pending": True, "active": None, "prepared": {"old-spawn": "old-unit"},
                    "units": {"old-unit": {"result": {"decisions": {
                        "subagent": {"choice": "child-fast", "confidence": 0.8}}}}}}
        path.write_text(json.dumps(previous))
        self.send("SessionStart", source="resume")
        current = json.loads(path.read_text())
        self.assertEqual(current["version"], 3)
        self.assertEqual(current["enabled"], ["skill", "subagent"])
        self.assertEqual(current["units"], {})
        self.assertEqual(current["prepared"], {})
        self.router.assert_not_called()

    def test_live_matrix_bounds_and_extra_host_models(self):
        self.enable("subagent")
        self.prompt()
        spawn = {"task_name": "reader", "message": "Summarize a module", "fork_turns": "none"}
        original = unit(("subagent",), target="subagent", spawn=spawn)
        cases = []
        for values in (["low"] * 2, [str(index) for index in range(17)], [None], "low"):
            data = copy.deepcopy(original)
            data["efforts"]["child-fast"] = values
            cases.append(data)
        too_many = copy.deepcopy(original)
        too_many["efforts"].update({"unused-" + str(index): [] for index in range(254)})
        cases.append(too_many)
        for data in cases:
            with self.subTest(data=data), self.assertRaises(gate.GateError) as error:
                self.begin(data)
            self.assertEqual(error.exception.code, "invalid_input")
        self.router.assert_not_called()
        original["efforts"]["unused-host-model"] = ["low"]
        self.assertEqual(self.begin(original)["decisions"]["subagent"]["model"], "child-fast")
        self.router.assert_called_once()

    def test_child_pair_concurrent_duplicate_and_continuation_reuse_one_route(self):
        self.enable("subagent")
        self.prompt()
        spawn = {"task_name": "reader", "message": "Summarize a module", "fork_turns": "none"}
        data = unit(("subagent",), target="subagent", spawn=spawn)
        self.router.side_effect = lambda request: (time.sleep(0.1), recommendation(request))[1]
        results = []
        threads = [threading.Thread(target=lambda: results.append(self.begin(data))) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3)
        self.assertEqual(len(results), 4)
        self.assertEqual(sum(not result["cached"] for result in results), 1)
        for result in results:
            self.assertEqual(result["decisions"]["subagent"]["model"], "child-fast")
            self.assertEqual(result["decisions"]["subagent"]["effort"], "low")
        self.prompt("Continue that same child task", turn="turn-b")
        continued = copy.deepcopy(data)
        continued["turn_id"] = "turn-b"
        self.assertTrue(self.begin(continued)["cached"])
        self.router.assert_called_once()

    def test_child_pair_http_failure_is_cached_without_fabricated_model_or_effort(self):
        self.enable("subagent")
        self.prompt()
        spawn = {"task_name": "reader", "message": "Summarize a module", "fork_turns": "none",
                 "model": "child-deep", "reasoning_effort": "high"}
        data = unit(("subagent",), target="subagent", spawn=spawn)
        self.router.side_effect = route.RoutingError("http_error")
        result = self.begin(data)
        self.assertEqual(result["status"], "fallback")
        self.assertEqual(result["decisions"], {})
        self.assertTrue(self.begin(data)["cached"])
        self.assertEqual(self.send("PreToolUse", tool_name="spawn_agent", tool_input=spawn), {})
        self.router.assert_called_once()

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
        self.assertEqual(first["decisions"]["skill"]["choices"], ["testing", "docs"])
        self.assertNotIn("task_model_application", first)
        self.assertNotIn("model", first)
        self.assertEqual(self.read(), {})
        self.assertEqual(self.read(), {})
        self.router.assert_called_once()

    def test_independent_children_remain_prepared_and_route_in_parallel(self):
        self.enable("skill subagent")
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
            data = unit(("skill", "subagent"), target="subagent", unit_id="child-" + str(index),
                        spawn=spawn, efforts={"child-fast": ["low"], "child-deep": ["high"]})
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
        self.assertIn("ordinary skill workflow", result["message"])
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
        self.enable("skill subagent")
        self.prompt()
        self.assertEqual(self.read(turn_id="child-turn"), {})
        for data, code in ((unit(()), "decision_scope_mismatch"),
                           (unit(turn_id="old-turn"), "stale_turn")):
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
        self.enable("subagent")
        self.prompt()
        spawn = {"task_name": "reader", "message": "Summarize a module", "fork_turns": "none"}
        for index, choice in enumerate(("not-in-inventory", [], None)):
            data = unit(("subagent",), target="subagent", spawn=spawn,
                        unit_id="bad-router-" + str(index))
            result = recommendation(data["request"])
            result["decisions"]["subagent"]["choice"] = choice
            self.router.side_effect = None
            self.router.return_value = result
            self.assertEqual(self.begin(data)["status"], "fallback")
            self.assertTrue(self.begin(data)["cached"])
        self.assertEqual(self.router.call_count, 3)

    def test_controls_support_explicit_invocations_and_independent_off(self):
        for prefix in ("jev", "$jev", "$shuaigle:jev", "/jev", "/shuaigle:jev"):
            self.send("UserPromptSubmit", prompt=prefix + " on all", turn_id="control")
            self.send("UserPromptSubmit", prompt=prefix + " off subagent", turn_id="control")
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
        self.assertIn(b"main model stays unchanged", result.stdout)
        self.assertNotIn(b"current_model", result.stdout)
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
        self.enable("skill")
        self.prompt()
        body = {"model": "jev-test", "answers": {
            "skill_0": {"type": "choice", "choice": "select", "confidence": 0.8,
                        "probabilities": {"select": 0.8, "skip": 0.2}},
            "skill_1": {"type": "choice", "choice": "skip", "confidence": 0.8,
                        "probabilities": {"select": 0.2, "skip": 0.8}}}}
        response = MagicMock(status=200)
        response.read.return_value = json.dumps(body).encode()
        self.router.side_effect = REAL_ROUTE
        with patch.object(route.http.client, "HTTPSConnection") as connection:
            connection.return_value.getresponse.return_value = response
            result = self.begin()
            self.assertEqual(result["decisions"]["skill"]["choices"], ["testing"])
            self.begin()
            self.read()
            self.read()
            connection.return_value.request.assert_called_once()
            payload = json.loads(connection.return_value.request.call_args.kwargs["body"])
            self.assertEqual(set(payload["questions"]), {"skill_0", "skill_1"})
            self.assertNotIn("session-a", json.dumps(payload))

    def test_bare_on_batches_child_skills_and_model_in_one_real_router_request(self):
        self.send("UserPromptSubmit", prompt="jev on", turn_id="control")
        self.prompt()
        spawn = {"task_name": "reader", "message": "Summarize a bounded module",
                 "fork_turns": "none", "model": "child-deep", "reasoning_effort": "high"}
        data = unit(("skill", "subagent"), target="subagent", unit_id="child-reader",
                    spawn=spawn, efforts={"child-fast": ["low"], "child-deep": ["high"]})
        body = {"model": "jev-test", "answers": {
            "subagent": {"type": "choice", "choice": "fast-low", "confidence": 0.8,
                         "probabilities": {"fast-low": 0.8, "deep-high": 0.2}},
            "skill_0": {"type": "choice", "choice": "select", "confidence": 0.8,
                        "probabilities": {"select": 0.8, "skip": 0.2}},
            "skill_1": {"type": "choice", "choice": "select", "confidence": 0.8,
                        "probabilities": {"select": 0.8, "skip": 0.2}}}}
        response = MagicMock(status=200)
        response.read.return_value = json.dumps(body).encode()
        self.router.side_effect = REAL_ROUTE
        with patch.object(route.http.client, "HTTPSConnection") as connection:
            connection.return_value.getresponse.return_value = response
            result = self.begin(data)
            self.assertEqual(result["decisions"]["skill"]["choices"], ["testing", "docs"])
            self.assertNotIn("model", result)
            self.assertNotIn("task_model_application", result)
            self.assertTrue(self.begin(data)["cached"])
            rewritten = self.send("PreToolUse", tool_name="spawn_agent", tool_input=spawn)
            self.assertEqual(rewritten["hookSpecificOutput"]["updatedInput"],
                             {**spawn, "model": "child-fast", "reasoning_effort": "low"})
            connection.return_value.request.assert_called_once()
            payload = json.loads(connection.return_value.request.call_args.kwargs["body"])
            self.assertEqual(set(payload["questions"]), {"subagent", "skill_0", "skill_1"})
            self.assertNotIn("current_model", payload["state"])
            self.assertNotIn("session-a", json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
