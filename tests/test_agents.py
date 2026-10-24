"""Mock-only contracts for the five provider CLIs; never invokes real models."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
TASKFILE = ROOT / "Taskfile.yml"
DEFINITION = yaml.safe_load(TASKFILE.read_text(encoding="utf-8"))
SCRIPT = DEFINITION["tasks"]["run"]["cmds"][0]
AGENTS = ("claude", "codex", "copilot", "opencode", "pi")


class AgentTaskfileTests(unittest.TestCase):
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
            "'cwd': os.getcwd(), 'prompt_in_env': 'ATF_PROMPT' in os.environ}, f)\n"
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
            "ATF_CODEX_SANDBOX": "read-only",
            "ATF_COPILOT_ALLOW_TOOL": "",
        })
        env.update(extras)
        return env

    def run_script(self, agent, prompt="Inspect this repo", **extras):
        self.capture.unlink(missing_ok=True)
        result = subprocess.run(
            ["sh", "-c", SCRIPT],
            cwd=self.workspace,
            env=self.environment(agent, prompt, **extras),
            capture_output=True,
            text=True,
        )
        recorded = json.loads(self.capture.read_text(encoding="utf-8")) if self.capture.exists() else None
        return result, recorded

    def test_schema_is_self_contained_and_public_tasks_delegate(self):
        self.assertEqual(DEFINITION["version"], "3")
        self.assertNotIn("includes", DEFINITION)
        self.assertIn("run", DEFINITION["tasks"])
        self.assertEqual(DEFINITION["tasks"]["run"]["dir"], "{{.USER_WORKING_DIR}}")
        for agent in AGENTS:
            cmd = DEFINITION["tasks"][agent]["cmds"][0]
            self.assertEqual(cmd["task"], "run")
            self.assertEqual(cmd["vars"]["AGENT"], agent)

    def test_headless_arguments_and_working_directory(self):
        expected = {
            "claude": ["-p", "Inspect this repo"],
            "codex": ["exec", "--sandbox", "read-only", "Inspect this repo"],
            "copilot": ["-p", "Inspect this repo", "-s", "--no-ask-user"],
            "opencode": ["run", "Inspect this repo"],
            "pi": ["-p", "Inspect this repo"],
        }
        for agent, arguments in expected.items():
            with self.subTest(agent=agent):
                result, captured = self.run_script(agent)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(captured["command"], agent)
                self.assertEqual(captured["args"], arguments)
                self.assertEqual(Path(captured["cwd"]), self.workspace)
                self.assertFalse(captured["prompt_in_env"])

    def test_model_is_optional_and_forwarded_to_every_cli(self):
        for agent in AGENTS:
            with self.subTest(agent=agent):
                result, captured = self.run_script(agent, ATF_MODEL="test/provider-model")
                self.assertEqual(result.returncode, 0, result.stderr)
                idx = captured["args"].index("--model")
                self.assertEqual(captured["args"][idx + 1], "test/provider-model")

    def test_prompt_metacharacters_are_literal_arguments(self):
        marker = self.root / "INJECTION"
        prompt = f"Try $(touch {marker}); 'quoted' \"$HOME\"\nUnicode 🌱"
        for agent in AGENTS:
            with self.subTest(agent=agent):
                result, captured = self.run_script(agent, prompt)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(captured["args"].count(prompt), 1)
                self.assertFalse(marker.exists(), "Prompt interpreted by shell")

    def test_prompt_file_and_validation(self):
        file = self.workspace / "instructions.md"
        file.write_text("Read the tests.\nReport failures.\n", encoding="utf-8")
        result, captured = self.run_script("pi", "", ATF_PROMPT_FILE="instructions.md")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(captured["args"][-1], "Read the tests.\nReport failures.")

        for prompt, kwargs in [
            ("", {}),
            ("text", {"ATF_PROMPT_FILE": "instructions.md"}),
            ("", {"ATF_PROMPT_FILE": "nonexistent.md"}),
        ]:
            with self.subTest(prompt=prompt, kwargs=kwargs):
                result, captured = self.run_script("pi", prompt, **kwargs)
                self.assertEqual(result.returncode, 2)
                self.assertIsNone(captured)

    def test_copilot_permissions_must_be_explicit(self):
        result, captured = self.run_script("copilot", ATF_COPILOT_ALLOW_TOOL="shell(git:*)")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(captured["args"][-2:], ["--allow-tool", "shell(git:*)"])
        self.assertNotIn("--allow-all", captured["args"])

    def test_codex_workspace_write_opt_in(self):
        result, captured = self.run_script("codex", ATF_CODEX_SANDBOX="workspace-write")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(captured["args"][:3], ["exec", "--sandbox", "workspace-write"])

        result, captured = self.run_script("codex", ATF_CODEX_SANDBOX="danger-full-access")
        self.assertEqual(result.returncode, 2)
        self.assertIsNone(captured)

    def test_unknown_agent_denied(self):
        result, captured = self.run_script("not-a-provider")
        self.assertEqual(result.returncode, 2)
        self.assertIsNone(captured)

    def test_missing_cli_returns_127(self):
        (self.bin / "pi").unlink()
        if shutil.which("pi") is not None:
            self.skipTest("Real Pi binary is on PATH")
        result, captured = self.run_script("pi")
        self.assertEqual(result.returncode, 127)
        self.assertIsNone(captured)

    @unittest.skipUnless(shutil.which("task"), "Go-task not installed locally; runs in CI")
    def test_go_task_local_include_dispatches_from_caller_directory(self):
        result = subprocess.run(
            ["task", "--taskfile", str(ROOT / "examples" / "Taskfile.yml"),
             "agents:claude", "PROMPT=Hello from caller", "MODEL=sonnet"],
            cwd=self.workspace,
            env={
                **os.environ,
                "PATH": str(self.bin) + os.pathsep + os.environ.get("PATH", ""),
                "ATF_TEST_CAPTURE": str(self.capture),
            },
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        captured = json.loads(self.capture.read_text(encoding="utf-8"))
        self.assertEqual(captured["command"], "claude")
        self.assertEqual(captured["args"], ["-p", "--model", "sonnet", "Hello from caller"])
        self.assertEqual(Path(captured["cwd"]), self.workspace)


if __name__ == "__main__":
    unittest.main()
