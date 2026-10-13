"""Offline alias resolver tests; every child process is mocked."""

import io
import json
import subprocess
import threading
import time
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

import claude_models


def request(aliases=None):
    return {"aliases": aliases if aliases is not None else ["haiku"], "expected_version": "2.1.296"}


def init(model="claude-haiku-5-5", version="2.1.296"):
    return json.dumps({"type": "system", "subtype": "init", "model": model,
                       "claude_code_version": version})


class ResolverTests(unittest.TestCase):
    def test_invalid_candidates_never_start_process(self):
        for data in (None, [], {}, request(["private/model"]), request(["haiku", "haiku"]),
                     request(["claude-haiku-5-5"]), {**request(), "extra": True},
                     {**request(), "expected_version": "/private/cli"}, request([{}])):
            with self.subTest(data=data), patch.object(claude_models.subprocess, "run") as run:
                with self.assertRaises(ValueError):
                    claude_models.resolve(data)
                run.assert_not_called()

    def test_local_status_resolves_exact_init_model(self):
        with patch.object(claude_models.subprocess, "run", return_value=SimpleNamespace(
                returncode=0, stdout=init())) as run:
            self.assertEqual(claude_models.resolve(request()), {
                "status": "resolved", "models": {"haiku": "claude-haiku-5-5"}})
        argv = run.call_args.args[0]
        self.assertEqual(argv[:4], ["claude", "-p", "/status", "--model"])
        for flag in ("--bare", "--no-session-persistence", "--strict-mcp-config"):
            self.assertIn(flag, argv)
        self.assertEqual(argv[argv.index("--tools") + 1], "")
        self.assertEqual(argv[argv.index("--setting-sources") + 1], "")
        self.assertNotIn("--max-turns", argv)
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertGreater(run.call_args.kwargs["timeout"], 0)
        self.assertLessEqual(run.call_args.kwargs["timeout"], 4)

    def test_wrong_missing_private_or_duplicate_init_is_unavailable(self):
        outputs = ["", "not JSON", "{}", init("haiku"), init("arn:aws:private"),
                   init("/private/model"), init(version="2.1.283"), init() + "\n" + init(),
                   json.dumps({"type": "result", "model": "claude-haiku-5-5"}),
                   "x" * (claude_models.MAX_BYTES + 1)]
        for output in outputs:
            with self.subTest(output=output[:60]), patch.object(claude_models.subprocess, "run",
                    return_value=SimpleNamespace(returncode=0, stdout=output)):
                self.assertEqual(claude_models.resolve(request())["models"], {})

    def test_probe_environment_isolates_auth_and_user_settings(self):
        private_env = {"PATH": "/test/bin", "HOME": "/private/user", "JEV_API_KEY": "router-secret",
                       "ANTHROPIC_API_KEY": "anthropic-secret", "CLAUDE_CODE_OAUTH_TOKEN": "oauth-secret",
                       "CLAUDE_CODE_USE_BEDROCK": "1", "AWS_SECRET_ACCESS_KEY": "aws-secret",
                       "ANTHROPIC_BASE_URL": "https://private.example", "CLAUDE_CONFIG_DIR": "/private/config",
                       "ANTHROPIC_DEFAULT_HAIKU_MODEL": "claude-haiku-5-5"}
        with patch.dict(claude_models.os.environ, private_env, clear=True):
            env = claude_models.probe_environment("/test/temp")
        self.assertEqual(env["PATH"], "/test/bin")
        self.assertEqual(env["HOME"], "/test/temp")
        self.assertEqual(env["CLAUDE_CONFIG_DIR"], "/test/temp")
        self.assertEqual(env["ANTHROPIC_DEFAULT_HAIKU_MODEL"], "claude-haiku-5-5")
        self.assertEqual(env["ANTHROPIC_BASE_URL"], "http://127.0.0.1:1")
        for name in ("JEV_API_KEY", "ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN",
                     "CLAUDE_CODE_USE_BEDROCK", "AWS_SECRET_ACCESS_KEY"):
            self.assertNotIn(name, env)
        self.assertNotIn("secret", json.dumps(env))

    def test_config_override_is_only_local_argv_and_never_output(self):
        with patch.dict(claude_models.os.environ, {"JEV_CLAUDE_BINARY": "/test/native/claude"}), patch.object(
                claude_models.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=init())) as run:
            result = claude_models.resolve(request())
        self.assertEqual(run.call_args.args[0][0], "/test/native/claude")
        self.assertNotIn("/test/native", json.dumps(result))

    def test_failed_or_timed_out_children_return_only_generic_unavailable(self):
        for error in (subprocess.TimeoutExpired("claude private token", 4), OSError("private secret")):
            with self.subTest(error=type(error)), patch.object(claude_models.subprocess, "run", side_effect=error):
                self.assertEqual(claude_models.resolve(request()), {"status": "unavailable", "models": {}})
        with patch.object(claude_models.subprocess, "run", return_value=SimpleNamespace(returncode=1, stdout=init())):
            self.assertEqual(claude_models.resolve(request())["status"], "unavailable")

    def test_expired_shared_budget_never_starts_child(self):
        with patch.object(claude_models.time, "monotonic", return_value=6), patch.object(
                claude_models.subprocess, "run") as run:
            self.assertIsNone(claude_models.probe("haiku", "2.1.296", "claude", "/test", 5))
            run.assert_not_called()

    def test_child_that_finishes_after_the_shared_deadline_is_ignored(self):
        with patch.object(claude_models.time, "monotonic", side_effect=[1, 6]), patch.object(
                claude_models.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=init())) as run:
            self.assertIsNone(claude_models.probe("haiku", "2.1.296", "claude", "/test", 5))
        self.assertEqual(run.call_args.kwargs["timeout"], 4)

    def test_four_aliases_run_concurrently_under_one_budget(self):
        ready = threading.Barrier(4)
        def local_status(argv, **kwargs):
            ready.wait(timeout=1)
            alias = argv[argv.index("--model") + 1]
            return SimpleNamespace(returncode=0, stdout=init("claude-" + alias + "-test"))
        start = time.monotonic()
        with patch.object(claude_models.subprocess, "run", side_effect=local_status) as run:
            result = claude_models.resolve(request(["haiku", "sonnet", "opus", "fable"]))
        self.assertEqual(len(result["models"]), 4)
        self.assertEqual(run.call_count, 4)
        self.assertLess(time.monotonic() - start, 2)
        self.assertLess(claude_models.TOTAL_SECONDS, 5)

    def test_main_redacts_invalid_input_and_errors(self):
        for text in ("private secret malformed", json.dumps(request(["/private/model"]))):
            output = io.StringIO()
            with patch.object(claude_models.sys, "stdin", io.StringIO(text)), redirect_stdout(output), patch.object(
                    claude_models.subprocess, "run") as run:
                self.assertEqual(claude_models.main(), 1)
            self.assertEqual(json.loads(output.getvalue()), {"status": "unavailable", "models": {}})
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
