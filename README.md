# taskfile-agents

**Reusable, headless Go-task commands** for five coding-agent CLIs, with one common interface:

| Task | Actual CLI invocation | Default permission posture |
|---|---|---|
| `agents:claude` | `claude -p ...` | Uses your Claude Code configuration; no permission bypass |
| `agents:codex` | `codex exec --sandbox read-only ...` | Read-only sandbox; explicitly opt into workspace-write |
| `agents:copilot` | `copilot -p ... -s --no-ask-user` | No broad tool permission grants; optional allowlist |
| `agents:opencode` | `opencode run ...` | Uses your OpenCode configuration; no `--auto` |
| `agents:pi` | `pi -p ...` | Uses your Pi configuration |

This is an **execution adapter library**, not a durable workflow engine. Each agent CLI must be installed and authenticated separately. The Taskfile contains no install scripts, model API keys, provider defaults, or auto-approved permissions.

## Requirements

- [Task](https://taskfile.dev/installation/), **v3.53.0+ for remote includes** (local includes also work with older v3).
- At least one of the CLI executables: `claude`, `codex`, `copilot`, `opencode`, `pi`.
- A POSIX-compatible shell environment; recommended: macOS, Linux, or Windows/WSL. `PROMPT_FILE` and `INSTRUCTIONS_FILE` use `cat`.

## Quickstart: local repository

Clone this repository, then:

```bash
task --list
task claude PROMPT='Explain this project without making changes'
task codex PROMPT='Review the architecture'
task copilot PROMPT='Summarize recent commits'
task opencode PROMPT='Investigate the test suite'
task pi PROMPT='Find potential bugs'
```

The five named tasks call a single `run` dispatcher. All are headless, return the subprocess exit status, and stream the provider output to your terminal. **Running an agent can consume model credits or write files** depending on the provider's configuration and permissions.

## Reuse from another repository

To reuse the published release, add the following to the consuming project's `Taskfile.yml`. Pin the reviewed release tag or a commit SHA so future updates cannot silently change the commands you run:

```yaml
version: '3'
includes:
  agents: https://github.com/tbrandenburg/taskfile-agents.git//Taskfile.yml?ref=v0.1.1
```

Then run from the consuming project:

```bash
task agents:claude PROMPT='Review the current diff'
task agents:codex PROMPT='Find bugs' MODEL='gpt-5.3-codex'
task agents:copilot PROMPT='Summarize the repo'
task agents:opencode PROMPT='Explain this project' MODEL='anthropic/claude-sonnet-4'
task agents:pi PROMPT='Review the tests'
```

The model examples are illustrative: use model IDs actually available in your respective CLI account. Task requires initial remote-source trust; review the remote YAML and pin to a **tag or commit SHA** rather than a moving branch. See [Remote Taskfiles](https://taskfile.dev/docs/remote-taskfiles).

You may also invoke the single remote Taskfile directly:

```bash
task --taskfile 'https://github.com/tbrandenburg/taskfile-agents.git//Taskfile.yml?ref=v0.1.1' \
  codex PROMPT='Review this repository'
```

## Inputs

| Variable | Meaning | Default |
|---|---|---|
| `PROMPT` | Text sent to the agent | empty (must provide it or `PROMPT_FILE`) |
| `PROMPT_FILE` | Read prompt content from a local file | empty |
| `MODEL` | Raw CLI-specific selector, passed as one quoted `--model` value | omitted (CLI chooses its configured model) |
| `FORMAT` | Exactly `text` or `jsonl`; selects native CLI output | `text` |
| `INSTRUCTIONS_FILE` | Local trusted UTF-8 Markdown prepended to the user prompt | omitted |
| `CODEX_SANDBOX` | `read-only` or `workspace-write` | `read-only` |
| `COPILOT_ALLOW_TOOL` | One Copilot `--allow-tool` value (may be a comma-separated set supported by Copilot) | omitted |
| `AGENT` | Agent name, for `agents:run` only | required |

Exactly one of `PROMPT` and `PROMPT_FILE` must be set. The code **never inserts the prompt into shell source**. The prompt, model, and Copilot tool allowlist are passed as individual quoted arguments so `;`, `$()`, quotes, multiline text, and unicode are not executed as shell syntax. The runner unsets its `ATF_PROMPT`, `ATF_PROMPT_FILE`, and `ATF_INSTRUCTIONS_FILE` environment carriers before launching the agent, but the combined instructions and prompt still appear in the agent process's command-line arguments and should **not contain secrets**.

### Long prompts in files

```bash
task agents:pi PROMPT_FILE=prompts/review.md
task agents:claude PROMPT_FILE=prompts/review.md MODEL=sonnet
```

Relative prompt file paths resolve against the **caller project's working directory**. Output is streamed; redirect stdout if you want to capture it (some CLIs also print progress to stderr):

```bash
task agents:codex PROMPT_FILE=prompts/report.md > report.md
```

### Output format

`FORMAT=text` leaves the CLI's native text/default output unchanged. `FORMAT=jsonl` selects its native JSON Lines event output using these flags:

| CLI | Flags added for `FORMAT=jsonl` |
|---|---|
| Claude | `--output-format stream-json --verbose` |
| Codex | `--json` |
| Copilot | `--output-format json` |
| OpenCode | `--format json` |
| Pi | `--mode json` |

```bash
task agents:opencode PROMPT='Explain this project' FORMAT=jsonl > events.jsonl
```

Stdout contains the native events; diagnostics remain on stderr. Event schemas vary by CLI and version: the adapter does not normalize them or enforce a shared response schema. Values other than `text` and `jsonl` are rejected before launching a provider.

### Trusted instructions from a file

Use `INSTRUCTIONS_FILE` to reuse trusted UTF-8 Markdown alongside a required task prompt:

```bash
printf '# Review guidance\nReport findings with file paths.\n' > review-instructions.md
task agents:claude INSTRUCTIONS_FILE=review-instructions.md PROMPT='Review the current diff'
```

The runner validates the required `PROMPT` or `PROMPT_FILE` before reading instructions; instructions alone cannot replace the task prompt. A supplied instructions path must be a readable regular file. Missing, nonregular, unreadable, empty, and newline-only instruction files are rejected before provider launch. Relative instruction paths, like prompt paths, resolve against the **caller project's working directory**.

Composition is exactly `instructions + "\n\n" + prompt`, passed as one user-prompt argument. Shell `cat` command substitution strips trailing newline characters from `INSTRUCTIONS_FILE` and `PROMPT_FILE`; inline `PROMPT` trailing newlines are preserved. Other content is passed literally, without Markdown parsing or UTF-8 validation.

This is **user-prompt text**, not a native system-prompt override, skill loader, or security boundary. Only use instruction files you trust. Native CLI configuration and permission behavior remain unchanged.

### Editing with Codex

For write-capable Codex tasks, explicitly enable workspace writes:

```bash
task agents:codex PROMPT='Fix the failing unit tests' CODEX_SANDBOX=workspace-write
```

This starter deliberately does not expose Codex's `danger-full-access` or permission-bypass flags. It also never supplies `--auto` (OpenCode), `--allow-all` (Copilot), or `--dangerously-skip-permissions` (Claude).

For Copilot, if the workflow needs to read Git history, grant only that tool:

```bash
task agents:copilot PROMPT='Explain the last 3 commits' COPILOT_ALLOW_TOOL='shell(git:*)'
```

`--no-ask-user` prevents conversational follow-ups; it does not silently authorize every tool. Unapproved tool requests may fail. Permission behavior for other providers depends on their own user/project configuration.

### Generic dispatch

```bash
task agents:run AGENT=opencode PROMPT='Find broken tests'
```

Good for a workflow whose agent is selected at runtime:

```yaml
version: '3'
includes:
  agents: https://github.com/tbrandenburg/taskfile-agents.git//Taskfile.yml?ref=v0.1.1
tasks:
  review:
    cmds:
      - task: agents:run
        vars:
          AGENT: '{{.AGENT | default "codex"}}'
          PROMPT: 'Review the current git diff. Do not modify files.'
```

## Release and pin

This repository already exists at [tbrandenburg/taskfile-agents](https://github.com/tbrandenburg/taskfile-agents).

The latest published release is **[v0.1.1](https://github.com/tbrandenburg/taskfile-agents/releases/tag/v0.1.1)**. Reference `?ref=v0.1.1` (or a reviewed commit SHA) in consumer includes instead of a moving `main` branch. Review imported YAML before trusting it.

### Publishing future releases

Once changes have passed the `Validate Taskfiles` GitHub Actions workflow on `main`, add matching notes at `docs/releases/vX.Y.Z.md` and publish a reviewed version:

```bash
git switch main
git pull --ff-only
git tag -a vX.Y.Z -m 'vX.Y.Z'
git push origin vX.Y.Z
gh release create vX.Y.Z --verify-tag --title vX.Y.Z --notes-file docs/releases/vX.Y.Z.md
```

Replace `X.Y.Z` with the next version number. The initial `v0.1.0` release was published by a one-time workflow, which is no longer needed.

## Tests

No real agent is invoked by the tests: temporary executable shims record argument arrays, working directories, and the presence of prompt-related environment carriers. Contracts cover native text/JSONL flags, raw model forwarding, instruction composition, invalid inputs, and literal metacharacter transport; they do not validate live provider event schemas.

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

If Go-task is installed, tests also exercise the local include in `examples/Taskfile.yml` with the CLI shims, checking caller-relative files and option forwarding for the five providers. CI installs Task via `go-task/setup-task@v2`.

## Limitations

- This is CLI orchestration, not native session or artifact management; there are no retries, persistent execution IDs, DAG scheduling, or human approvals.
- The `MODEL` option forwards a raw model selector, which varies by provider.
- Copilot and Claude may require explicit project trust/permissions for tools when executed non-interactively.
- Importing external YAML executes shell commands with your privileges. Always review and pin third-party Taskfiles.
- Remote Taskfiles are self-contained: this file deliberately does not depend on scripts in the publishing repository.

## CLI documentation

- [OpenCode CLI](https://dev.opencode.ai/docs/cli/)
- [Pi project](https://github.com/earendil-works/pi)
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code/cli-usage)
- [GitHub Copilot CLI automation](https://docs.github.com/en/copilot/how-tos/copilot-cli/automate-copilot-cli/run-cli-programmatically)
- [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)
- [Go-task remote includes](https://taskfile.dev/docs/remote-taskfiles)

## License

MIT
