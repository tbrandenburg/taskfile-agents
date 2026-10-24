"""Mock-only contracts for the five provider CLIs; never invokes real models."""
from pathlib import Path
import shutil
import unittest

from agents_fixture import AGENTS, DEFINITION, SCRIPT, AgentFixture


class AgentTaskfileTests(AgentFixture):
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
            for format in (None, "text"):
                with self.subTest(agent=agent, format=format):
                    env = self.environment(agent)
                    if format is None:
                        env.pop("ATF_FORMAT")
                    result, captured = self.run_command(["sh", "-c", SCRIPT], env)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(captured["command"], agent)
                    self.assertEqual(captured["args"], arguments)
                    self.assertEqual(Path(captured["cwd"]), self.workspace)
                    self.assertEqual(captured["carriers"], [])

    def test_model_is_optional_and_forwarded_to_every_cli(self):
        model = 'raw model/雪; $(touch MODEL_INJECTION) `touch MODEL_INJECTION` "$HOME"\nnext'
        expected = {
            "claude": ["-p", "--model", model, "Inspect this repo"],
            "codex": ["exec", "--sandbox", "read-only", "--model", model, "Inspect this repo"],
            "copilot": ["-p", "Inspect this repo", "-s", "--no-ask-user", "--model", model],
            "opencode": ["run", "--model", model, "Inspect this repo"],
            "pi": ["-p", "--model", model, "Inspect this repo"],
        }
        for agent, arguments in expected.items():
            with self.subTest(agent=agent):
                result, captured = self.run_script(agent, ATF_MODEL=model)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(captured["args"], arguments)
                self.assertFalse((self.workspace / "MODEL_INJECTION").exists())

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
        result, captured = self.run_task("claude", "PROMPT=Hello from caller", "MODEL=sonnet")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(captured["command"], "claude")
        self.assertEqual(captured["args"], ["-p", "--model", "sonnet", "Hello from caller"])
        self.assertEqual(Path(captured["cwd"]), self.workspace)


if __name__ == "__main__":
    unittest.main()
