# AGENTS.md

## Lessons Learned

- 2026-10-24: Pitfall: CLI retries hid a connection failure behind long smoke-test timeouts. Prevention: Disable retries for a bounded diagnostic invocation and reproduce directly with the CLI before attributing failures to adapter flags or model selection.
