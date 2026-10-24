"""Shared CLI shims for Taskfile contract tests; no real model calls."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
TASKFILE = ROOT / "Taskfile.yml"
DEFINITION = yaml.safe_load(TASKFILE.read_text(encoding="utf-8"))
SCRIPT = DEFINITION["tasks"]["run"]["cmds"][0]
AGENTS = ("claude", "codex", "copilot", "opencode", "pi")
CARRIERS = ("ATF_PROMPT", "ATF_PROMPT_FILE", "ATF_INSTRUCTIONS_FILE")


class AgentFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "project"
        self.workspace.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.capture = self.root / "args.json"
        mock = (
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "with open(os.environ['ATF_TEST_CAPTURE'], 'w', encoding='utf-8') as f:\n"
            "  json.dump({'command': os.path.basename(sys.argv[0]), 'args': sys.argv[1:], "
            "'cwd': os.getcwd(), 'carriers': [name for name in "
            f"{CARRIERS!r} if name in os.environ]}}, f)\n"
            "print('mock-agent-success')\n"
        )
        for agent in AGENTS:
            path = self.bin / agent
            path.write_text(mock, encoding="utf-8")
            path.chmod(0o755)

    def environment(self, agent, prompt="Inspect this repo", **extras):
        env = os.environ.copy()
        env.update({
            "PATH": str(self.bin) + os.pathsep + os.environ.get("PATH", ""),
            "ATF_TEST_CAPTURE": str(self.capture),
            "ATF_AGENT": agent,
            "ATF_PROMPT": prompt,
            "ATF_PROMPT_FILE": "",
            "ATF_MODEL": "",
            "ATF_FORMAT": "text",
            "ATF_INSTRUCTIONS_FILE": "",
            "ATF_CODEX_SANDBOX": "read-only",
            "ATF_COPILOT_ALLOW_TOOL": "",
        })
        env.update(extras)
        return env

    def run_command(self, command, env):
        self.capture.unlink(missing_ok=True)
        result = subprocess.run(
            command, cwd=self.workspace, env=env,
            capture_output=True, text=True, timeout=15,
        )
        recorded = json.loads(self.capture.read_text(encoding="utf-8")) if self.capture.exists() else None
        return result, recorded

    def run_script(self, agent, prompt="Inspect this repo", **extras):
        return self.run_command(["sh", "-c", SCRIPT], self.environment(agent, prompt, **extras))

    def run_task(self, agent, *variables):
        env = os.environ.copy()
        env.update({
            "PATH": str(self.bin) + os.pathsep + os.environ.get("PATH", ""),
            "ATF_TEST_CAPTURE": str(self.capture),
        })
        return self.run_command(
            ["task", "--taskfile", str(ROOT / "examples" / "Taskfile.yml"),
             f"agents:{agent}", *variables],
            env,
        )
