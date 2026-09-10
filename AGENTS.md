<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **agent-code-intel** (1801 symbols, 3696 relationships, 49 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/agent-code-intel/context` | Codebase overview, check index freshness |
| `gitnexus://repo/agent-code-intel/clusters` | All functional areas |
| `gitnexus://repo/agent-code-intel/processes` | All execution flows |
| `gitnexus://repo/agent-code-intel/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
<!-- code-intel:start -->
## Code intelligence

Use the repo-scoped `agent-code-intel-routing` skill for code exploration,
debugging, reviews, refactoring, implementation, architecture, and dependency
analysis. Codex discovers it automatically; other agents must read
`.agents/skills/agent-code-intel-routing/SKILL.md`. The skill is the source of
truth for choosing between GrepAI, GitNexus, and ripgrep. Keep GitNexus safety
requirements for impact analysis, graph-aware renames, and change detection.

Never hand-edit `.grepai/config.yaml`; run `agent-code-intel --apply` to repair
generated configuration.

After a task changes code, run `agent-code-intel --refresh` from the project
root. If the command or its local stack is unavailable, report that and
continue; code intelligence is a navigation aid, not a correctness gate.
Docs-only changes do not need a refresh.

Before reading a source file, use the `code-context` skill: derive the exact
definition range with `ctags` instead of guessing a line window, and use
`rg`/`ast-grep` — not the knowledge graphs — for exhaustive reference lists.
<!-- code-intel:end -->
