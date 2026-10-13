#!/usr/bin/env python3
"""Resolve offered aliases through the matching Claude CLI's local /status."""

import concurrent.futures
import json
import os
import re
import subprocess
import sys
import tempfile
import time


ALIASES = {"sonnet", "opus", "haiku", "fable"}
TOTAL_SECONDS = 4.5
CHILD_SECONDS = 4
MAX_BYTES = 131072
MODEL_ID = re.compile(r"claude-[a-z0-9][a-z0-9.-]{0,120}\Z")
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9._-]+)?\Z")
MODEL_ENV = ("ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
             "ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_DEFAULT_FABLE_MODEL",
             "ANTHROPIC_SMALL_FAST_MODEL")


def validate_input(data):
    if (not isinstance(data, dict) or set(data) != {"aliases", "expected_version"}
            or not isinstance(data["aliases"], list) or len(data["aliases"]) > 4
            or not all(isinstance(alias, str) and alias in ALIASES for alias in data["aliases"])
            or len(set(data["aliases"])) != len(data["aliases"])
            or not isinstance(data["expected_version"], str)
            or not VERSION.fullmatch(data["expected_version"])):
        raise ValueError("invalid_input")
    return data["aliases"], data["expected_version"]


def probe_environment(config_dir):
    allowed = ("PATH", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT", "PATHEXT") + MODEL_ENV
    env = {name: os.environ[name] for name in allowed if name in os.environ}
    env.update({"HOME": config_dir, "CLAUDE_CONFIG_DIR": config_dir,
                "ANTHROPIC_BASE_URL": "http://127.0.0.1:1",
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                "DISABLE_TELEMETRY": "1", "DISABLE_ERROR_REPORTING": "1"})
    return env


def parse_init(stdout, expected_version):
    if not isinstance(stdout, str) or len(stdout.encode("utf-8")) > MAX_BYTES:
        return None
    inits = []
    for line in stdout.splitlines():
        try:
            item = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(item, dict) and item.get("type") == "system" and item.get("subtype") == "init":
            inits.append(item)
    if len(inits) != 1:
        return None
    item = inits[0]
    model = item.get("model")
    return model if (item.get("claude_code_version") == expected_version
                     and isinstance(model, str) and MODEL_ID.fullmatch(model)) else None


def probe(alias, version, binary, config_dir, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return None
    argv = [binary, "-p", "/status", "--model", alias, "--bare", "--output-format", "stream-json",
            "--verbose", "--no-session-persistence", "--setting-sources", "", "--tools", "",
            "--strict-mcp-config"]
    try:
        result = subprocess.run(argv, env=probe_environment(config_dir), stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                timeout=min(CHILD_SECONDS, remaining), check=False)
        if result.returncode != 0 or time.monotonic() >= deadline:
            return None
        return parse_init(result.stdout, version)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def resolve(data):
    aliases, version = validate_input(data)
    if not aliases:
        return {"status": "resolved", "models": {}}
    deadline = time.monotonic() + TOTAL_SECONDS
    binary = os.environ.get("JEV_CLAUDE_BINARY", "claude")
    models = {}
    with tempfile.TemporaryDirectory(prefix="jev-models-") as directory:
        # At most four bounded children run concurrently under one deadline.
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(probe, alias, version, binary,
                                       os.path.join(directory, alias), deadline): alias for alias in aliases}
            for future, alias in futures.items():
                try:
                    model = future.result(timeout=max(0, deadline - time.monotonic()))
                    if model:
                        models[alias] = model
                except Exception:
                    future.cancel()
    return {"status": "resolved" if models else "unavailable", "models": models}


def main():
    try:
        raw = sys.stdin.read(4097)
        if len(raw) > 4096:
            raise ValueError("invalid_input")
        result = resolve(json.loads(raw))
    except Exception:
        result = {"status": "unavailable", "models": {}}
    print(json.dumps(result))
    return 0 if result["status"] == "resolved" else 1


if __name__ == "__main__":
    sys.exit(main())
