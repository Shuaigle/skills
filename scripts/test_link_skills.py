"""Exercise link-skills.sh in disposable directories without changing HOME."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("link-skills.sh")


class LinkSkillsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="skill-links-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "repo"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for command in ("bash", "dirname", "find", "basename", "readlink", "mkdir", "rm", "ln"):
            executable = shutil.which(command)
            self.assertIsNotNone(executable, command)
            (self.bin / command).symlink_to(executable)
        (self.bin / "python3").symlink_to(sys.executable)
        for name in ("alpha", "beta"):
            source = self.repo / "skills" / name
            source.mkdir(parents=True)
            (source / "SKILL.md").write_text(f"# {name}\n")
        self.script = self.repo / "scripts" / "link-skills.sh"
        self.script.parent.mkdir()
        text = SCRIPT.read_text()
        for harness in ("claude", "agents"):
            original = f'$HOME/.{harness}/skills'
            self.assertIn(original, text)
            text = text.replace(original, f'$SKILL_LINK_TEST_ROOT/{harness}/skills')
        self.script.write_text(text)
        self.claude = self.root / "destinations" / "claude" / "skills"
        self.codex = self.root / "destinations" / "agents" / "skills"
        self.env = os.environ.copy()
        self.env.update(PATH=str(self.bin), SKILL_LINK_TEST_ROOT=str(self.root / "destinations"))

    def registry(self, value, exit_code=0):
        self.env["SKILL_LINK_TEST_JSON"] = value if isinstance(value, str) else json.dumps(value)
        self.env["SKILL_LINK_TEST_EXIT"] = str(exit_code)
        stub = self.bin / "claude"
        stub.write_text(
            '#!/usr/bin/env bash\n'
            '[ "$*" = "plugin list --json" ] || exit 90\n'
            'if [ "$SKILL_LINK_TEST_EXIT" != 0 ]; then\n'
            '  echo "private query diagnostic" >&2\n'
            '  exit "$SKILL_LINK_TEST_EXIT"\n'
            'fi\n'
            'printf "%s" "$SKILL_LINK_TEST_JSON"\n'
        )
        stub.chmod(0o755)

    def run_links(self, success=True):
        result = subprocess.run(
            [str(self.bin / "bash"), str(self.script)],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def assert_linked(self, destination):
        for name in ("alpha", "beta"):
            link = destination / name
            self.assertTrue(link.is_symlink(), str(link))
            self.assertEqual(os.readlink(link), str(self.repo / "skills" / name))

    def assert_claude_skipped(self, result):
        self.assertFalse(self.claude.exists())
        self.assert_linked(self.codex)
        self.assertNotIn("private query diagnostic", result.stdout + result.stderr)

    def test_installed_plugin_skips_claude(self):
        self.registry([{"id": "shuaigle@shuaigle", "enabled": True}])
        result = self.run_links()
        self.assert_claude_skipped(result)
        self.assertIn("已安裝 shuaigle plugin", result.stdout)

    def test_disabled_plugin_from_another_marketplace_still_skips_claude(self):
        self.registry([
            {"id": "other@marketplace", "enabled": True},
            {"id": "shuaigle@local-marketplace", "enabled": False},
        ])
        self.assert_claude_skipped(self.run_links())

    def test_absent_plugin_links_both_harnesses(self):
        self.registry([{"id": "other@marketplace", "description": "shuaigle@shuaigle"}])
        self.run_links()
        self.assert_linked(self.claude)
        self.assert_linked(self.codex)

    def test_empty_registry_links_both_harnesses(self):
        self.registry([])
        self.run_links()
        self.assert_linked(self.claude)
        self.assert_linked(self.codex)

    def test_no_claude_cli_keeps_existing_behavior(self):
        self.run_links()
        self.assert_linked(self.claude)
        self.assert_linked(self.codex)

    def test_query_failure_skips_claude_and_still_links_codex(self):
        self.registry([], exit_code=1)
        result = self.run_links()
        self.assert_claude_skipped(result)
        self.assertIn("warning:", result.stderr)

    def test_malformed_json_skips_claude_and_still_links_codex(self):
        self.registry("{private broken registry")
        result = self.run_links()
        self.assert_claude_skipped(result)
        self.assertIn("warning:", result.stderr)
        self.assertNotIn("private broken registry", result.stdout + result.stderr)

    def test_unrecognized_registry_schema_skips_claude(self):
        for registry in ({"installed": []}, [{"id": None}], [{"name": "shuaigle"}], ["shuaigle@local"]):
            with self.subTest(registry=registry):
                self.registry(registry)
                result = self.run_links()
                self.assert_claude_skipped(result)
                self.assertIn("warning:", result.stderr)

    def test_missing_python_skips_claude_and_still_links_codex(self):
        self.registry([])
        (self.bin / "python3").unlink()
        result = self.run_links()
        self.assert_claude_skipped(result)
        self.assertIn("Python 3", result.stderr)

    def test_installed_plugin_leaves_all_claude_entries_untouched(self):
        self.registry([{"id": "shuaigle@shuaigle"}])
        self.claude.mkdir(parents=True)
        (self.claude / "alpha").symlink_to(self.repo / "skills" / "alpha")
        (self.claude / "old").symlink_to(self.repo / "skills" / "deleted")
        foreign = self.root / "foreign"
        foreign.mkdir()
        (self.claude / "beta").symlink_to(foreign)
        (self.claude / "local").mkdir()
        self.run_links()
        self.assertEqual(os.readlink(self.claude / "alpha"), str(self.repo / "skills" / "alpha"))
        self.assertEqual(os.readlink(self.claude / "old"), str(self.repo / "skills" / "deleted"))
        self.assertEqual(os.readlink(self.claude / "beta"), str(foreign))
        self.assertTrue((self.claude / "local").is_dir())
        self.assert_linked(self.codex)

    def test_other_source_entries_are_preserved_and_only_own_stale_links_pruned(self):
        self.registry([])
        foreign = self.root / "foreign"
        foreign.mkdir()
        for destination in (self.claude, self.codex):
            destination.mkdir(parents=True)
            (destination / "alpha").symlink_to(foreign)
            (destination / "beta").mkdir()
            (destination / "old").symlink_to(self.repo / "skills" / "deleted")
            (destination / "foreign-old").symlink_to(foreign / "deleted")
        result = self.run_links()
        for destination in (self.claude, self.codex):
            self.assertEqual(os.readlink(destination / "alpha"), str(foreign))
            self.assertTrue((destination / "beta").is_dir())
            self.assertFalse((destination / "beta").is_symlink())
            self.assertFalse((destination / "old").is_symlink())
            self.assertEqual(os.readlink(destination / "foreign-old"), str(foreign / "deleted"))
        self.assertIn("不覆蓋", result.stderr)

    def test_destination_symlink_into_repo_is_rejected_before_writes(self):
        self.registry([])
        self.claude.parent.mkdir(parents=True)
        self.claude.symlink_to(self.repo / "skills")
        result = self.run_links(success=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("指向本 repo", result.stderr)
        self.assertFalse((self.repo / "skills" / "alpha").is_symlink())
        self.assertFalse(self.codex.exists())


if __name__ == "__main__":
    unittest.main()
