# Agent Code Intelligence

This context describes how `agent-code-intel` exposes code-search capabilities
to coding agents working in a repository.

## Language

**Agent target**:
The selected instruction consumer: `claude`, `codex`, or `both`. It controls
which agent-specific MCP registrations, documents, and routing skills apply.
_Avoid_: Agent type, client

**Routing skill**:
The repo-scoped `agent-code-intel-routing` skill that chooses between GrepAI,
GitNexus, and ripgrep for a codebase task.
_Avoid_: Search instructions, code-intel block

**Managed agent artifact**:
An agent document block or routing skill explicitly owned by
`agent-code-intel`, so the tool may update or remove it without touching
surrounding user content.
_Avoid_: Generated file, agent config
