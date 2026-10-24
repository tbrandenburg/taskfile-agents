"""MODEL, FORMAT, and trusted instruction transport contracts."""
import os
from pathlib import Path
import shutil
import unittest

from agents_fixture import AGENTS, AgentFixture


class AgentOptionsTests(AgentFixture):
    def test_jsonl_exact_arguments_with_optional_raw_model(self):
        for model in ("", 'raw/雪 model; $(touch MODEL_INJECTION) `touch MODEL_INJECTION` "$HOME"\nnext'):
            option = ["--model", model] if model else []
            expected = {
                "claude": ["-p", *option, "--output-format", "stream-json", "--verbose", "Inspect this repo"],
                "codex": ["exec", "--sandbox", "read-only", *option, "--json", "Inspect this repo"],
                "copilot": ["-p", "Inspect this repo", "-s", "--no-ask-user", *option, "--output-format", "json"],
                "opencode": ["run", *option, "--format", "json", "Inspect this repo"],
                "pi": ["-p", *option, "--mode", "json", "Inspect this repo"],
            }
            for agent, arguments in expected.items():
                with self.subTest(agent=agent, model=model):
                    result, captured = self.run_script(agent, ATF_FORMAT="jsonl", ATF_MODEL=model)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(captured["args"], arguments)
                    self.assertFalse((self.workspace / "MODEL_INJECTION").exists())

    def test_invalid_format_prevents_provider_launch(self):
        for agent in AGENTS:
            for format in ("json", "JSONL", "text jsonl", "jsonl; touch FORMAT_INJECTION"):
                with self.subTest(agent=agent, format=format):
                    result, captured = self.run_script(agent, ATF_FORMAT=format)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("FORMAT must be text or jsonl", result.stderr)
                    self.assertIsNone(captured)
                    self.assertFalse((self.workspace / "FORMAT_INJECTION").exists())

    def test_instructions_compose_once_without_native_system_flags(self):
        instructions = '# Trusted 雪\nKeep "quotes", \'apostrophes\', $HOME; $(touch INJECTION) `touch INJECTION`'
        prompt = 'Review "this" repo; $(touch INJECTION)\nPreserve 雪 and $HOME\n\n'
        path = "trusted 雪 'quotes' $(touch PATH_INJECTION).md"
        (self.workspace / path).write_text(instructions + "\n\n\n", encoding="utf-8")
        (self.workspace / "prompt file.md").write_text(prompt, encoding="utf-8")
        for source in ("inline", "file"):
            composed = instructions + "\n\n" + (prompt if source == "inline" else prompt.rstrip("\n"))
            expected = {
                "claude": ["-p", composed],
                "codex": ["exec", "--sandbox", "read-only", composed],
                "copilot": ["-p", composed, "-s", "--no-ask-user"],
                "opencode": ["run", composed],
                "pi": ["-p", composed],
            }
            for agent, arguments in expected.items():
                with self.subTest(agent=agent, source=source):
                    result, captured = self.run_script(
                        agent, prompt if source == "inline" else "",
                        ATF_PROMPT_FILE="" if source == "inline" else "prompt file.md",
                        ATF_INSTRUCTIONS_FILE=path,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(captured["args"], arguments)
                    self.assertEqual(captured["args"].count(composed), 1)
                    self.assertEqual(captured["carriers"], [])
                    self.assertFalse((self.workspace / "INJECTION").exists())
                    self.assertFalse((self.workspace / "PATH_INJECTION").exists())

    def test_invalid_instruction_files_prevent_provider_launch(self):
        (self.workspace / "directory.md").mkdir()
        (self.workspace / "empty.md").touch()
        (self.workspace / "newlines.md").write_text("\n\n\n", encoding="utf-8")
        cases = {
            "missing.md": "does not exist or is not regular",
            "directory.md": "does not exist or is not regular",
            "empty.md": "Set a non-empty INSTRUCTIONS_FILE",
            "newlines.md": "Set a non-empty INSTRUCTIONS_FILE",
        }
        for agent in AGENTS:
            for path, message in cases.items():
                with self.subTest(agent=agent, path=path):
                    result, captured = self.run_script(agent, ATF_INSTRUCTIONS_FILE=path)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn(message, result.stderr)
                    self.assertIsNone(captured)

    @unittest.skipIf(os.geteuid() == 0, "Root can read mode-000 files; requires an unprivileged user")
    def test_unreadable_instruction_file_prevents_provider_launch(self):
        path = self.workspace / "unreadable.md"
        path.write_text("Trusted instructions", encoding="utf-8")
        self.addCleanup(path.chmod, 0o600)
        path.chmod(0)
        for agent in AGENTS:
            with self.subTest(agent=agent):
                result, captured = self.run_script(agent, ATF_INSTRUCTIONS_FILE=path.name)
                self.assertEqual(result.returncode, 2)
                self.assertIn("Unable to read INSTRUCTIONS_FILE", result.stderr)
                self.assertIsNone(captured)

    def test_instructions_do_not_replace_required_prompt_validation(self):
        (self.workspace / "valid.md").write_text("Trusted instructions", encoding="utf-8")
        (self.workspace / "empty-prompt.md").write_text("\n\n", encoding="utf-8")
        for agent in AGENTS:
            for instructions in ("valid.md", "missing.md"):
                for promptfile in ("", "empty-prompt.md"):
                    with self.subTest(agent=agent, instructions=instructions, promptfile=promptfile):
                        result, captured = self.run_script(
                            agent, "", ATF_PROMPT_FILE=promptfile, ATF_INSTRUCTIONS_FILE=instructions,
                        )
                        self.assertEqual(result.returncode, 2)
                        self.assertIn("Set a non-empty PROMPT or PROMPT_FILE", result.stderr)
                        self.assertIsNone(captured)

    @unittest.skipUnless(shutil.which("task"), "Go-task not installed locally; runs in CI")
    def test_go_task_include_transports_options_and_caller_relative_files(self):
        path = "trusted 雪 'quotes' $(touch PATH_INJECTION).md"
        instructions = '# Rules 雪\nPreserve "quotes"; $HOME $(touch INJECTION) `touch INJECTION`'
        prompt = 'Caller "prompt" 雪\n$HOME; $(touch INJECTION)'
        model = 'provider/raw 雪 "model"; $(touch MODEL_INJECTION)\nnext'
        (self.workspace / path).write_text(instructions + "\n\n", encoding="utf-8")
        (self.workspace / "prompt 雪 'file'.md").write_text(prompt + "\n\n", encoding="utf-8")
        composed = instructions + "\n\n" + prompt
        expected = {
            "claude": ["-p", "--model", model, "--output-format", "stream-json", "--verbose", composed],
            "codex": ["exec", "--sandbox", "read-only", "--model", model, "--json", composed],
            "copilot": ["-p", composed, "-s", "--no-ask-user", "--model", model, "--output-format", "json"],
            "opencode": ["run", "--model", model, "--format", "json", composed],
            "pi": ["-p", "--model", model, "--mode", "json", composed],
        }
        for agent, arguments in expected.items():
            for source in (f"PROMPT={prompt}", "PROMPT_FILE=prompt 雪 'file'.md"):
                with self.subTest(agent=agent, source=source):
                    result, captured = self.run_task(
                        agent, source, "FORMAT=jsonl", f"MODEL={model}", f"INSTRUCTIONS_FILE={path}",
                    )
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(captured["command"], agent)
                    self.assertEqual(captured["args"], arguments)
                    self.assertEqual(Path(captured["cwd"]), self.workspace)
                    self.assertEqual(captured["carriers"], [])
                    for marker in ("INJECTION", "PATH_INJECTION", "MODEL_INJECTION"):
                        self.assertFalse((self.workspace / marker).exists())


if __name__ == "__main__":
    unittest.main()
