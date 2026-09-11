<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **agent-code-intel** (1558 symbols, 3883 relationships, 62 execution flows).

> Index stale? Run `node .gitnexus/run.cjs analyze --index-only` from the project root — it auto-selects an available runner. No `.gitnexus/run.cjs` yet? Bootstrap with `npx`, `bunx`, or `pnpm dlx` — e.g. `bunx gitnexus@latest analyze` (npm 11 npx crash; #1939).

## Always Do

- **MUST run impact before editing.** Use `impact({target: "symbolName", direction: "upstream"})` or `node .gitnexus/run.cjs impact "symbolName" --direction upstream --repo .`; report callers, processes, and risk. Never substitute grep for graph analysis.
- **MUST analyze graph changes before committing.** Use `detect_changes({scope: "all"})` (MCP) or `node .gitnexus/run.cjs detect-changes --scope all --repo .` (CLI fallback). `partial: true` or `truncated: true` is not a clean check — a zero means unseen, not unaffected; re-run it. For regression review: `detect_changes({scope: "compare", base_ref: "main"})` or `node .gitnexus/run.cjs detect-changes --scope compare --base-ref "main" --repo .`.
- MUST warn on HIGH/CRITICAL `risk` pre-edit; never use `riskSharedAxes` to waive a HIGH/CRITICAL `risk` warning. Compare File/symbol: MCP File omits axes; Graph-RAG expands File.
- **MUST treat `risk: UNKNOWN` as unresolved, not as low.** An empty caller set is not evidence the symbol is unused — it can also mean the callers are not resolvable by the index (plain-object property access, dynamic dispatch, cross-language calls). `impact` pairs `UNKNOWN` with a `riskNote` saying so. Confirm with a text search before treating the symbol as safe to change or delete; do not proceed on the strength of a zero.
- **MUST use `query({search_query: "concept"})` for concepts/flows, `context({name: "symbolName"})` for a named symbol, or `impact` for blast radius, on read-only callers, dependencies, imports, or execution flow.** Graph first; text search only for empty/`UNKNOWN`/literals.
- For security review, `explain({target: "fileOrSymbol"})` lists taint findings (source→sink flows; needs `analyze --pdg`).

## Never Do

- NEVER edit a function, class, or method before MCP/CLI impact analysis.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis, and never read `UNKNOWN` as an all-clear — it means the walk could not answer, which is the one verdict that requires confirming by other means.
- NEVER rename symbols with find-and-replace — use `rename` which understands the call graph.
- NEVER commit before MCP/CLI graph change analysis.

## Resources

| Resource | Use for |
| --- | --- |
| `gitnexus://repo/agent-code-intel/context` | Codebase overview, check index freshness |
| `gitnexus://repo/agent-code-intel/clusters` | All functional areas |
| `gitnexus://repo/agent-code-intel/processes` | All execution flows |
| `gitnexus://repo/agent-code-intel/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
| --- | --- |
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
<!-- code-intel:start -->
## Code intelligence

Use the repo-scoped `agent-code-intel-routing` skill for code exploration,
debugging, reviews, refactoring, implementation, architecture, and dependency
analysis. Claude discovers it at
`.claude/skills/agent-code-intel-routing/SKILL.md`. It is the source of truth
for choosing between GrepAI, GitNexus, and ripgrep. Keep GitNexus safety
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

## Agent skills

### Issue tracker

Issues live as GitHub issues in `eduardtomasek/agent-code-intel`, driven by the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles, each label string equal to its name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root, both created lazily when something is actually resolved. See `docs/agents/domain.md`.

## Changelog and README

When a change is finished and a user would notice it — behaviour or a default
changes, a bug is fixed, a flag/message/exit code/JSON key comes or goes, a
requirement is raised — do two documentation steps **before** the commit and
before reporting the work as done:

- **MUST add an entry under `## [Unreleased]` in `CHANGELOG.md`** — Czech, Keep
  a Changelog categories, explaining what changed and why, with `(#NN)` when
  there is an issue or PR.
- **MUST check `README.md` is still in sync** with the new behaviour (flag and
  exit-code tables, requirements, error messages, version strings) and update
  what drifted. Verify with `rg`, don't assume; report either "README updated:
  …" or "README checked, no drift".

Not every edit earns an entry. Internal refactors and renames with no
observable difference, formatting, comments, typos, docs-only and test-only
changes stay out — don't pad the changelog. When you leave a change out, say so
in a sentence. See `docs/agents/changelog.md` for the threshold, the README
section map and the release procedure.
