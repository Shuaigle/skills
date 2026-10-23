"""Public-boundary tests for Claude native combined-routing receipts."""

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import claude_route as receipts
import route


SECRET = "test-key-never-persist"
SKILLS = [{"id": "testing", "description": "Write behavioral tests"},
          {"id": "docs", "description": "Write documentation"}]
OPTIONS = [{"id": "fast-low", "model": "haiku", "effort": "low",
            "description": "Fast child with low reasoning"},
           {"id": "deep-high", "model": "opus", "effort": "high",
            "description": "Deep child with high reasoning"}]


def request(subagent=True):
    decisions = {"skill": SKILLS}
    if subagent:
        decisions["subagent"] = OPTIONS
    return {"host": "Claude Code", "task": "Review a bounded module and report findings",
            "decisions": decisions}


def prepared(**fields):
    data = {"session_id": "session-a", "original": {"model": None, "effort": None},
            "request": request()}
    data.update(fields)
    return data


def recommendation(data):
    decisions = {"skill": {"choices": ["testing"], "evaluations": {}}}
    if "subagent" in data["decisions"]:
        decisions["subagent"] = {"choice": "deep-high", "model": "opus", "effort": "high",
                                 "confidence": 0.8, "probabilities": {"deep-high": 0.8, "fast-low": 0.2}}
    return {"status": "recommended", "host": data["host"], "router_model": "jev-test",
            "decisions": decisions}


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patch.dict(os.environ, {"JEV_API_KEY": SECRET, "CLAUDE_CODE_SESSION_ID": ""}).start()
        self.router = patch.object(route, "route", side_effect=recommendation).start()
        self.addCleanup(patch.stopall)

    def begin(self, data=None):
        return receipts.begin(prepared() if data is None else data, self.tmp.name)

    def claim(self, receipt, session="session-a", spawn="spawn-1", **fields):
        data = {"session_id": session, "receipt_id": receipt["receipt_id"], "spawn": spawn,
                "model": receipt["model"], "effort": receipt["effort"],
                "brief_line": receipt["brief_line"]}
        data.update(fields)
        return receipts.claim(data, self.tmp.name)

    def error(self, call, *args, **fields):
        with self.assertRaises(receipts.ReceiptError) as raised:
            call(*args, **fields)
        return raised.exception

    def test_successful_route_returns_the_pair_skills_and_a_brief_line(self):
        receipt = self.begin()
        self.assertEqual(receipt["status"], "recommended")
        self.assertEqual((receipt["model"], receipt["effort"], receipt["skills"]),
                         ("opus", "high", ["testing"]))
        line = receipt["brief_line"]
        self.assertTrue(line.startswith("Jev routing: "))
        self.assertNotIn("\n", line)
        self.assertEqual(json.loads(line[len("Jev routing: "):]),
                         {"receipt": receipt["receipt_id"], "model": "opus", "effort": "high",
                          "skills": ["testing"]})
        self.router.assert_called_once()

    def test_matching_spawn_claims_the_receipt_once(self):
        receipt = self.begin()
        claimed = self.claim(receipt)
        self.assertEqual(claimed["receipt"]["status"], "recommended")
        self.assertEqual(claimed["receipt"]["skills"], ["testing"])
        self.assertEqual(self.claim(receipt)["receipt"]["model"], "opus",
                         "repeated events of the same spawn reuse their claim")
        self.assertEqual(self.error(self.claim, receipt, spawn="spawn-2").code, "receipt_used")
        self.assertEqual(self.error(self.claim, receipt, spawn=None).code, "receipt_used")

    def test_unkeyed_spawn_claims_once(self):
        receipt = self.begin()
        self.claim(receipt, spawn=None)
        self.assertEqual(self.error(self.claim, receipt, spawn=None).code, "receipt_used")

    def test_missing_receipt_or_another_session_is_rejected(self):
        receipt = self.begin()
        self.assertEqual(self.error(self.claim, receipt, receipt_id="r-0000000000000000").code,
                         "receipt_missing")
        self.assertEqual(self.error(self.claim, receipt, session="session-b").code, "receipt_missing")
        self.claim(receipt)

    def test_model_effort_or_brief_mismatch_is_rejected_without_consuming(self):
        receipt = self.begin()
        for fields, code in (({"model": "haiku"}, "receipt_mismatch"),
                             ({"model": None}, "receipt_mismatch"),
                             ({"effort": "low"}, "receipt_mismatch"),
                             ({"effort": None}, "receipt_mismatch"),
                             ({"brief_line": receipt["brief_line"].replace("testing", "docs")},
                              "brief_mismatch")):
            with self.subTest(fields=fields):
                error = self.error(self.claim, receipt, **fields)
                self.assertEqual(error.code, code)
                self.assertEqual(error.expected, {"model": "opus", "effort": "high",
                                                  "brief_line": receipt["brief_line"]})
        self.claim(receipt)

    def test_receipts_expire(self):
        receipt = self.begin()
        later = receipts.time.time() + receipts.TTL_SECONDS + 1
        with patch.object(receipts.time, "time", return_value=later):
            self.assertEqual(self.error(self.claim, receipt).code, "receipt_expired")

    def test_routing_failure_writes_a_fallback_receipt_for_the_original_settings(self):
        self.router.side_effect = route.RoutingError("network_error")
        receipt = self.begin(prepared(original={"model": "sonnet", "effort": None}))
        self.assertEqual((receipt["status"], receipt["code"]), ("fallback", "network_error"))
        self.assertEqual((receipt["model"], receipt["effort"], receipt["skills"]), ("sonnet", None, []))
        self.assertIn("original spawn settings", receipt["message"])
        claimed = self.claim(receipt)["receipt"]
        self.assertEqual((claimed["status"], claimed["code"]), ("fallback", "network_error"))

    def test_missing_key_is_a_fallback_but_invalid_requests_leave_no_receipt(self):
        with patch.dict(os.environ, {"JEV_API_KEY": ""}):
            self.router.side_effect = route.RoutingError("missing_api_key")
            self.assertEqual(self.begin()["code"], "missing_api_key")
        self.router.side_effect = route.RoutingError("invalid_input")
        self.assertEqual(self.error(self.begin).code, "invalid_input")
        self.router.side_effect = recommendation
        bad = [prepared(request={**request(), "decisions": {"subagent": OPTIONS}}),
               prepared(original={"model": None}),
               prepared(original={"model": None, "effort": None}, extra=True),
               prepared(request=request(subagent=False)),
               prepared(skip_subagent="inventory_unavailable"),
               prepared(request=request(subagent=False), skip_subagent="other"),
               prepared(session_id="bad\nid")]
        for data in bad:
            with self.subTest(data=data):
                self.assertEqual(self.error(self.begin, data).code, "invalid_input")
        self.assertEqual(self.router.call_count, 2)

    def test_skipped_subagent_routes_skills_and_keeps_original_settings(self):
        receipt = self.begin(prepared(request=request(subagent=False),
                                      original={"model": "opus", "effort": "max"},
                                      skip_subagent="fixed_effort_unverified"))
        self.assertEqual((receipt["status"], receipt["model"], receipt["effort"], receipt["skills"]),
                         ("recommended", "opus", "max", ["testing"]))
        self.assertEqual(self.claim(receipt)["receipt"]["skip_subagent"], "fixed_effort_unverified")
        self.assertNotIn("subagent", self.router.call_args.args[0]["decisions"])

    def test_session_comes_from_the_host_environment_and_must_match_it(self):
        with patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "session-a"}):
            data = prepared()
            del data["session_id"]
            self.claim(self.begin(data))
            self.assertEqual(self.error(self.begin, prepared(session_id="session-b")).code,
                             "session_mismatch")
        data = prepared()
        del data["session_id"]
        self.assertEqual(self.error(self.begin, data).code, "invalid_input")

    def test_state_is_private_and_holds_no_key_task_or_brief(self):
        receipt = self.begin()
        self.claim(receipt)
        root = Path(self.tmp.name)
        self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
        files = [path for path in root.iterdir() if path.suffix == ".json"]
        self.assertEqual(len(files), 1)
        self.assertEqual(stat.S_IMODE(files[0].stat().st_mode), 0o600)
        raw = files[0].read_text()
        for private in (SECRET, "session-a", "Review a bounded module", "spawn-1",
                        "Write behavioral tests"):
            self.assertNotIn(private, raw)
        saved = json.loads(raw)["receipts"][receipt["receipt_id"]]
        self.assertEqual({key: saved[key] for key in ("model", "effort", "skills", "status")},
                         {"model": "opus", "effort": "high", "skills": ["testing"],
                          "status": "recommended"})
        self.assertIsInstance(saved["created"], int)

    def test_a_key_anywhere_in_the_input_is_refused_before_routing(self):
        data = prepared(original={"model": SECRET, "effort": None})
        self.assertEqual(self.error(self.begin, data).code, "unsafe_input")
        self.router.assert_not_called()

    def test_expired_receipts_are_pruned_and_session_receipts_are_bounded(self):
        old = self.begin()
        later = receipts.time.time() + receipts.TTL_SECONDS + 1
        with patch.object(receipts.time, "time", return_value=later):
            self.begin()
            saved = json.loads(next(Path(self.tmp.name).glob("*.json")).read_text())
            self.assertNotIn(old["receipt_id"], saved["receipts"])
            with patch.object(receipts, "MAX_RECEIPTS", 1):
                self.assertEqual(self.error(self.begin).code, "state_full")


class CommandLineTests(unittest.TestCase):
    def run_helper(self, args, data, state):
        return subprocess.run([sys.executable, str(Path(receipts.__file__)), *args],
                              input=json.dumps(data), capture_output=True, text=True,
                              env={**os.environ, "JEV_CLAUDE_STATE_DIR": state,
                                   "JEV_API_KEY": "", "CLAUDE_CODE_SESSION_ID": ""})

    def test_cli_reports_fallback_receipts_and_errors_as_json(self):
        with tempfile.TemporaryDirectory() as state:
            began = self.run_helper(["begin"], prepared(), state)
            self.assertEqual(began.returncode, 0, began.stdout)
            receipt = json.loads(began.stdout)
            self.assertEqual((receipt["status"], receipt["code"]), ("fallback", "missing_api_key"))
            claim = {"session_id": "session-a", "receipt_id": receipt["receipt_id"], "spawn": "s",
                     "model": None, "effort": None, "brief_line": receipt["brief_line"]}
            claimed = self.run_helper(["claim"], claim, state)
            self.assertEqual(claimed.returncode, 0, claimed.stdout)
            self.assertEqual(json.loads(claimed.stdout)["status"], "ok")
            refused = self.run_helper(["claim"], {**claim, "spawn": "t"}, state)
            self.assertEqual(refused.returncode, 1)
            self.assertEqual(json.loads(refused.stdout), {"status": "error", "code": "receipt_used"})
            self.assertEqual(self.run_helper(["other"], {}, state).returncode, 1)
            self.assertIn("begin", subprocess.run([sys.executable, str(Path(receipts.__file__)),
                                                   "--help"], capture_output=True, text=True).stdout)


if __name__ == "__main__":
    unittest.main()
