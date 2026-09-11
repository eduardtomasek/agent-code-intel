# Changelog and README Upkeep

When a change is big enough that a user would notice it, finishing it means two
documentation steps, not one: an entry in `CHANGELOG.md`, and a check that
`README.md` still describes the product as it now behaves. Do both **before**
you offer the work as done — before the commit, and before the PR body is
written. Smaller edits skip both; the threshold is below.

## When it applies

The changelog is for changes that actually matter to someone using the tool —
not a log of every edit. An entry is required when the change is observable
from outside the code:

- behaviour or a default changes,
- a bug is fixed,
- a flag, mode, message, exit code or JSON key is added, renamed or removed,
- a requirement is raised (Node, Python, a dependency version),
- anything else large enough that a user would be surprised to hit it without
  having been told.

No entry for the small stuff: internal refactors and renames with no observable
difference, formatting, comments, typo fixes, docs-only edits, test-only
changes, and edits to `CHANGELOG.md` or `README.md` themselves. Don't pad the
file — an entry nobody would act on is noise.

The test is simple: **would a user notice, or have to do something differently?**
If yes, it goes in. If you genuinely can't tell, say so and ask rather than
guessing either way.

## 1. Changelog entry

`CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/) and is
written **in Czech**, matching the surrounding entries.

- Add the entry under `## [Unreleased]`. Never invent a version heading; cutting
  a release is a separate, deliberate act (see below).
- Use the categories this file already uses, in this order:
  `### Breaking`, `### Přidáno`, `### Změněno`, `### Opraveno`,
  `### Odstraněno`, `### Testy`.
- Write what changed **and why** — the existing entries explain the reasoning,
  the old behaviour, and the concrete new message or key. A one-line "fixed a
  bug" is not in the house style.
- Reference the issue or PR as `(#NN)` when there is one.
- Anything that changes `--status --json`, a flag, a default, or an exit code
  belongs in the changelog even when it looks small; those are the repo's
  public contract.

## 2. README consistency check

`README.md` is the Czech end-user manual and drifts silently. After the
changelog entry, check the sections the change could have invalidated and fix
what no longer matches:

| If the change touched… | Check in README |
| --- | --- |
| A mode, flag, or positional argument | `### Referenční tabulka všech režimů a přepínačů` (§11) — the mode table, general switches, skip switches, per-mode switches |
| An exit code | `#### Návratové kódy` |
| A requirement (Node, Python, a tool version) | `### Verze Node.js musí být alespoň …`, `### Python 3.11+`, `### Závislosti ve třech úrovních` |
| A user-visible message or failure mode | `## 15. Když se něco pokazí` — the error headings are literal message texts |
| The dashboard | `## 14. Dashboard — přehled o všem najednou` |
| The everyday workflow | `## 13. Každodenní používání` |
| The product version | `## Aktualizace na X.Y.Z`, and any version string in `## Rychlý start` |

Verify, don't assume: grep the README for the flag, message, key or version you
changed (`rg -n -- '--no-hook' README.md`) rather than eyeballing the table of
contents. A flag that appears nowhere in the README after you added it is a
finding, not a non-event.

Report the outcome either way: "README updated: mode table + exit codes" or
"README checked, no drift". Silence reads as "not done".

## 3. Cutting a release (only when asked)

Releasing is not part of finishing a feature. When it is explicitly requested:

1. Rename `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD` and open a fresh empty
   `## [Unreleased]` above it.
2. Bump `__version__` in `agent_code_intel/__init__.py` — the single source of
   the product version.
3. Add the compare link at the bottom of `CHANGELOG.md` and repoint
   `[Unreleased]` at the new tag.
4. Update `## Aktualizace na X.Y.Z` in the README if the release is breaking.

Published tags are immutable: never retag a released version, fix forward.
