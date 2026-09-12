# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/),
versioning on [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `LICENSE` — the project is now released under the MIT License. Free private
  and commercial use, modification and redistribution; the only condition is
  that the license text and the attribution stay with the copies you
  distribute. README has a "License" section and a badge for it.

### Changed

- README is now entirely in English and carries badges in its header (license,
  release, platform, Python, Node.js, MCP). The content, the commands and the
  error messages do not change, only the language of the text.
- This changelog is now written in English, including all historical entries.
  Only the language changes, no record was added, removed or reworded in
  substance.

## [6.1.0] - 2026-09-11

### Added

- `code-intel-dash` 1.5.0 can pause and retire a project, not only show that it
  is idle. A stack that watches projects nobody works on any more burns CPU,
  disk and space in the vector database for nothing, and both remedies are
  per-project. Every project has two buttons:
  - **Pause indexing** / **Resume indexing** stops and restarts the GrepAI
    watcher of the given workspace; the index stays as it is. The dashboard
    remembers the pause in `<conf>/dash-paused.json`, so a paused project is
    grey with the `config ok` and `watcher paused` labels — not red with a
    "fix" of `--refresh` or `--apply`, which would cancel the pause.
    `agent-code-intel` counts a stopped watcher towards the project's `ok`; for
    a paused project the dashboard therefore reads the new `drift` list (below)
    and the config is fine when `watcher` is the only entry in it.
    `code-intel-dash --once` does not return 2 because of a pause. The note
    holds only until the watcher writes anything into its log: if `--refresh`
    or `--apply` starts it in the meantime, the pause is over, and if it then
    crashes, it is a red error again.
  - **Remove from code-intel…** stops the watcher after confirmation and takes
    the project out of the registry — and nothing more. `.grepai/`,
    `.gitnexus/`, the collection in qdrant, the routing skills and the block in
    `CLAUDE.md` all stay, so coming back costs no reindex. The dashboard
    remembers retired projects in `<conf>/dash-retired` and shows them at the
    bottom in the *Removed from code-intel* section with a **Bring back**
    button; a returned project still has its watcher paused. Deliberately this
    is not `--remove`, which deletes all of that: "stop watching a finished
    project" and "this is not a code-intel project any more" are two different
    things.

  Writes go only through a `POST` from the dashboard's own page: the server
  rejects a foreign `Host` (DNS rebinding), a foreign `Origin` and a request
  without the `X-Code-Intel` header, which a foreign page would have to ask for
  with a preflight that the server never answers. It takes the registry, the
  configuration directory and the project workspace from `agent_code_intel`,
  not from its own implementation, and it rewrites both the registry and the
  retired list under a lock — two retirements finishing at once would otherwise
  lose one project from both lists. The verdict about the watcher is its actual
  state, not the exit code of `grepai watch --background`, which returns 1
  after a minute of waiting even when the watcher is running.

  The dashboard JSON (`--once`, `/api/status`) has new keys: `paused` and
  `config_ok` on a project, `retired` (retired projects) and `action_error`
  (why actions do not work when the `agent_code_intel` package is missing) at
  the root. `--once` decides by `config_ok` instead of `ok`.

  Versions 1.2.0 and 1.4.0 were not released in this line — they carried
  work in progress on open issues. The dashboard therefore goes from 1.1.0 to
  1.3.0 and from there to 1.5.0; this number line is kept from here on. (#110)
- `--status --json` has a `drift` key on every project: the list of checks that
  failed, by name (`workspace`, `mapping`, `embedder`, `chunking`, `ignores`,
  `watcher`, `legacy_refresh_script`, `routing_skills`, `session_start_hook`;
  `code_intel` or `exists` on shortened lines). `ok` is exactly "the list is
  empty". Anyone who needs a verdict without one check — the dashboard, for a
  watcher it paused itself — asks the list and does not have to derive the rest
  of the verdict again. The key sits right before `ok`; no other key or their
  order changes. (#110)

### Changed

- The minimum Node.js version is **24.11.0** and it is taken from what GitNexus
  asks for, not from guessing by a single function. Until now preflight tested
  for the presence of `module.registerHooks`, which arrived in the 22.15 line —
  but gitnexus 1.6.11 declares `engines: ^22.18.0 || >=24.11.0`, so a Node
  between 22.15 and 22.18 passed the check even though GitNexus does not
  support it. Out of the declared range we take the upper branch as a single
  minimum; it is somewhat stricter than what GitNexus allows, but it is one
  number instead of two ranges. The message now says
  `node vX is below the 24.11.0 that gitnexus requires`.
- `--status --json` has two new keys under `tool.node`: `version_ok` (what the
  decision is made against) and `version_min`. `register_hooks` stays, because
  it names the exact symptom of an index built under an old Node.
  `code-intel-dash` takes its verdict from `version_ok`.
- README has a reference table of all modes, flags and exit codes in chapter
  10, verified against `--help`. Including the fact that `--status --json`
  returns zero even on breakage, because the state is read from the `ok` key.
- README states the 24.11.0 minimum in the component overview, in the
  requirements list, in the table of the three dependency levels, in chapter 7
  and in the dashboard description.
- `code-intel-dash` shows the Stack section as five rows under each other
  instead of a grid of cards. The cards wrapped by window width, so the MCP
  servers dropped onto another row by themselves on a normal monitor and the
  same values sat in a different place for every component — anyone looking for
  what was wrong had to read card by card. Now every component has the state
  and the name on the left, the values in five columns that line up across all
  rows on the right, and the warning with its fix right below them; a row that
  needs attention also has a tinted background. The Stack heading carries an
  `all ok` summary, or `N of 5 need attention` — MCP without a running server
  does not count, because that is an ordinary state. The data, the verdicts and
  the warning texts do not change. (#108)
- `code-intel-dash` is at version **1.3.0**. `--install` overwrites the
  dashboard only when its version differs from the installed one, so without a
  bump a machine with 1.1.0 would never get the new Stack layout from #108 —
  the installation would report `code-intel-dash 1.1.0 already installed` and
  leave the old copy. Version 1.2.0 is skipped: it is carried by a build from a
  fork (pausing and removing a project) which is not in this repository, and
  the installer could not tell two different dashboards with the same number
  apart. (#109)

### Fixed

- The configuration fix in the project overview in `code-intel-dash` always
  advised `agent-code-intel --path … --agent claude --apply`. Since 6.0.0,
  `--agent` overrides and rewrites the agents recorded in `.code-intel`, so for
  a project wired up for `both` the advice would silently switch the project to
  Claude only. The advice now names exactly the agents the `--status` line was
  judged against (the `agents` key). (#110)
- The read endpoints of `code-intel-dash` were open to a page using DNS
  rebinding: a foreign site redirected to 127.0.0.1 is the same origin for the
  browser, so it could read the report, run searches and read the returned code
  snippets. The `Host` header check, so far only on writes, now applies to
  every request. Further: `/api/files` reads the index from qdrant as
  `agent-code-intel` reported it and ignores the `url` parameter from the
  request (previously a POST to an arbitrary address could be sent through it);
  `ws` on the read endpoints has to be a valid workspace name; and the query
  for `grepai search` goes after `--`, so text starting with a dash is not a
  flag. (#110)

### Tests

- `test/unit/test_dash.py` is the first suite for the dashboard itself: pausing
  and its note (including two pauses at once and a watcher that crashes after a
  restart), retiring and bringing back over a real registry in a temporary
  tree including twelve retirements finishing at once, the `--once` verdict,
  and the gates in front of writes and reads against a real server on the
  loopback. GrepAI is a fake in-memory watcher in them and the configuration
  points into a temporary tree; the tests reach neither the real registry nor
  the real watcher. `DriftContractTest` verifies `config_ok` against a real
  `--status --json`. (#110)

## [6.0.0] - 2026-09-10

`.code-intel` remembers which agents the project was wired up for. The major
version goes up because of that file's schema, not because of the size of the
changes.

### Breaking

- `--apply` writes `.code-intel` in **schema 2** with an `AGENTS` key. Older
  versions of the tool refuse such a file with `unsupported SCHEMA=2`, so after
  a downgrade an `--apply` from that older version is needed. The other
  direction is fine: files with `SCHEMA=1` are still read and work unchanged,
  `--status` only adds a `.code-intel predates AGENTS` line for them, which is
  **not drift** — running `--apply` is therefore not mandatory.

### Added

- `.code-intel` remembers which agents the project was wired up for. `--apply`
  writes `AGENTS=claude|codex|both` and raises `SCHEMA` to `2`; `--status`,
  `--refresh` and `--remove` then work with exactly those agents without having
  to be told again every time. Previously the answer lived only on the command
  line, so a project wired up for Claude alone reported drift on a missing
  Codex routing skill and a missing Codex hook on every run without
  `--agent claude` — a red state that could not be cleared by anything except
  installing an agent the user does not care about. It was worked around with a
  wrapper on `PATH` or by typing the flag on every command; both are
  superfluous.
- `--status --all` resolves the agents for each project separately, so one
  machine can hold a Claude project and a both-agent project side by side and
  every line is compared against what that project actually has.
- The JSON from `--status --all --json` has two new keys on every project:
  `agents` (what the line was judged against) and `agents_recorded` (what its
  own file says, `null` on schema 1). No other key or their order changes.

### Changed

- `--apply` not only creates `.code-intel` but also rewrites it when the
  recorded agents differ from the ones it is being run with — `--agent` is
  therefore still the authority and it is the way to change the project's
  choice. An identical file stays unchanged byte for byte.
- The `Agents:` header in `--apply`, `--refresh`, `--status` and `--remove`
  also says where the value comes from: `(--agent)`, `(from .code-intel)`, or
  `(default)`.

## [5.1.0] - 2026-09-10

A small release: `--apply` ignores `.DS_Store` and preflight tells BSD `ctags`
from Universal Ctags.

### Fixed

- Preflight, `--status` and `--install-deps` distinguish BSD `ctags` from
  Universal Ctags (#99). macOS always has `/usr/bin/ctags`, so presence alone
  said nothing: a machine without `universal-ctags` from Homebrew got a green
  `ok ctags on PATH` and `--install-deps` reported that nothing was missing,
  while the command prescribed by the `code-context` skill did not work at all.
  It is now a `warn` with its own cause, distinct from a missing `ctags`, and
  `--install-deps` really does offer `universal-ctags`. `ctags` stays a
  recommended tool with a fallback to `ast-grep`, not a required dependency.

### Changed

- `--apply` adds `.DS_Store` to `.gitignore` next to `.grepai/` and
  `.gitnexus/`. Projects wired up by an older version report it as
  `.gitignore += …` drift until the first `--apply`; `_ensure_gitignore` adds
  only the missing lines, so a hand-maintained `.gitignore` keeps its order and
  content. It can be turned off through `gitignore_entries` in `defaults.toml`.

### Removed

- `docs/.DS_Store`, committed by mistake in `e87a298`.

## [5.0.0] - 2026-09-10

The release of our own code-context chain for Claude and Codex: managed skills,
repo-local `SessionStart` hooks and a check of the recommended tools.

### Breaking

- `--apply` now writes tool-owned repo-local `SessionStart` hooks and a second
  `code-context` skill; `--no-hook` is available for projects that manage their
  hooks themselves.

### Added

- A standalone `--install-deps` mode that checks nine tools and, on macOS,
  offers to install the available Homebrew packages after confirmation.
- A `SessionStart` hook for both Claude and Codex, and the three conditions for
  activating the Codex hook documented in README.
- `code-context` as a second byte-identical managed skill for both agents;
  status, refresh and remove distinguish its state and ownership.

### Changed

- `ctags` and `rg` are recommended tools with a fallback in preflight; missing
  `ast-grep`, `fd`, `rga`, `tokei` and `scc` are reported as recommendations.
- README states the verified languages, the procedure for unverified languages
  and the extended `--no-hook` and `--no-install-deps` options.

### Tests

- 292 unit tests and 53 hermetic black-box scenarios.
- The behavioural measurement of the code-context chain met the 80 % threshold:
  three out of three read operations in a fresh session used a derived range or
  the whole small file after verifying its size.
- The [acceptance report](docs/acceptance/5.0.0.md) captures the live
  verification of all project modes for `claude`, `codex` and `both` on clean
  projects, and a separate check of `--install-deps`.

- README rewritten into a shorter form: a shortened title, unified numbering of
  the contents and a new hero image (`hero.jpg`).

### Removed

- The frozen Bash reference harness, the differential scenarios and its shell
  helpers. The active Python test suite stays; the fixture for the supported
  migration of existing `refresh-intel.sh` projects is now a small Python
  helper.
- The shared `test/lib/isolated_path.sh` interpreter resolver; `test/unit.sh`
  now takes Python 3.11 directly and `ACI_PYTHON` selects a supplementary
  interpreter explicitly.

### Fixed

- A `.code-intel` with a space in a value can now be read back. `--apply`
  writes `PROJECT` as the bare directory basename without quotes, but
  `_LINE_RE` required `\S+`, so a project in a directory such as
  `CS Imager (test)` ended with a `malformed line` error on every further
  `--status` and `--refresh`. The value was widened to `.+`; key validation (a
  lowercase letter, a line without `=`, an empty value) does not change.

## [4.1.0] - 2026-09-09

The release of the managed routing skill for GrepAI, GitNexus and the optional
ripgrep, including safe distribution for Claude and Codex.

### Added

- `agent-code-intel-routing`: a byte-identical managed skill in
  `.claude/skills/` for Claude and `.agents/skills/` for Codex; `--agent
  claude|codex|both` determines which copies are created by `--apply`.
- A check of the skill in `--status`, `--status --json` and `--refresh`;
  `--remove` removes only the tool-owned copies and `.agents` is not indexed by
  GrepAI.
- A README with a quick start from the dependencies to `--apply`, an update
  guide and the optional `ripgrep` (`rg`) for exact search and verification.

### Changed

- `--install` now installs `code-intel-dash` as well; its own `VERSION` drives
  the dashboard update independently of the `agent-code-intel` version.
- An ordinary `--apply` is idempotent for the managed skill: it does not change
  a byte-identical file and repairs drift of a tool-owned file atomically.

### Removed

- Serena from the instructions of the new routing skill; the decision now uses
  GrepAI for meaning, GitNexus for relationships and `rg` for exact queries and
  verification.

### Tests

- 260 unit tests and 53 hermetic black-box scenarios cover the skill lifecycle,
  the agent choice, idempotence, drift, installation, status, refresh and
  remove.

## [4.0.0] - 2026-09-09

The release of the Python rewrite after switching the active entry point,
verifying the candidate SHA and three recorded live sessions.

### Breaking

- The v4 CLI requires Python 3.11 or newer and returns approved runtime
  diagnostics without a traceback on an older interpreter.
- The product version has a single source in `agent_code_intel.__version__`;
  the active `agent-code-intel` entry point is a Python launcher with the same
  runtime gate as the installed copy.

### Added

- A Python package and a standalone launcher for preview/apply, status, JSON
  status, refresh, remove and install/upgrade.
- A typed `defaults.toml` alongside the preserved compatibility with the
  executed `defaults.env`; the installation creates a TOML template only when
  no configuration exists.
- A safe `--remove` with a dry-run plan, ownership checks and an optional
  `--purge-collection`.
- An acceptance report with differential ENV/TOML lanes and a versioned
  historical audit in `docs/acceptance/`.

### Changed

- The installation copies the whole owned Python package, preserves the
  existing configuration and supports an upgrade from a v2, v3 and previous v4
  installation.
- `--status --json` keeps the agreed schema; `--refresh` and `--remove` keep the
  exit codes, the order of effects and the tolerated remote reference errors.
- README describes both configuration formats, Python 3.11+, the manual
  transition and the separate removal of the CLI, the configuration, the
  projects and the stack.

### Removed

- Nothing new is removed automatically beyond the owned installation artifacts,
  a pristine legacy script and managed blocks that explicitly belong to the
  tool.

### Tests

- The acceptance report in `docs/acceptance/4.0.0.md` captures the reference,
  candidate and final SHA, the hermetic ENV/TOML lanes and three live sessions
  on three repositories.
- The report states only the evidence actually produced; three different
  working days and a user-session/machine restart are not part of the corrected
  release scope.

## [3.0.0] - 2026-09-08

Merging `refresh-intel.sh` into `agent-code-intel --refresh` — the whole
wayfinder map
[#2](https://github.com/eduardtomasek/agent-code-intel/issues/2), slices
#11–#20.

### Breaking

- The tool was renamed from `code-intel-init` to `agent-code-intel`.
  `--install` deletes the old binary in `~/.local/bin/`; no compat symlink to
  the old name (#11).
- `refresh-intel.sh` is no longer generated or used. Existing repositories are
  migrated automatically on the first `--apply` after the update — an untouched
  generated copy is deleted, a hand-modified one is never deleted, only
  reported and left in place (#16).
- `--force-script` removed (#17).
- `--status --all --json` no longer returns the `project.N.script_state` key
  (#17).
- The rule in `~/.claude/settings.json` changed from the project-relative
  `Bash(./refresh-intel.sh)` to the global `Bash(agent-code-intel --refresh)`;
  `--install` removes the old rule automatically (#15).

### Added

- A new `--refresh` mode: it reindexes GitNexus, starts the GrepAI watcher if
  it is not running, and audits both. The exit codes were unified: `0` ok, `1`
  could not run, `2` drift (#14).
- The `.code-intel` file carries the identity of the repository (`WORKSPACE`,
  `PROJECT`) directly in the versioned repo. `--apply` creates it (#13); the
  tool reads it and prefers it over deriving from `basename` and over the
  registry (#12).
- Automatic migration of unmigrated repositories built straight into `--apply`
  — no separate flag (#16).

### Changed

- The block for AI agents in `CLAUDE.md`/`AGENTS.md` talks about a missing
  `agent-code-intel` command, not about a failed script; the full explanation
  of "why a failure does not matter" moved into `--help` (#18).
- `README.md` fully aligned with the new reality — the new binary name
  everywhere, `refresh-intel.sh` replaced by `--refresh`, a note added about
  the required reinstallation of `code-intel-dash` (#19).
- `code-intel-dash` (→ 1.1.0): fixed so that it can find the renamed binary —
  since #11 it could not find it at all until this slice repaired it — and it
  stopped reading the dropped `script_state` key (#17).

### Removed

- The `refresh-intel.sh` generator (`render_refresh()`, a ~310-line template)
  (#17).

### Tests

- The test suite was extended from 13 to 53, hermetically, without depending on
  the real stack. It is formally documented that the `--apply` happy path stays
  verified manually on a live stack, not by stubs — laid out in one place in
  `test/run.sh` (#20).

## [2.4.1] and earlier

The history before this CHANGELOG cannot be derived from the commits in this
repository: the tool arrived here in this version from an external source (see
`git log`, the `Hessevalentino/audit-fixes-dashboard-v2.4.1` merge), not from
development in this repo.

[Unreleased]: https://github.com/eduardtomasek/agent-code-intel/compare/v6.1.0...HEAD
[6.1.0]: https://github.com/eduardtomasek/agent-code-intel/compare/v6.0.0...v6.1.0
[6.0.0]: https://github.com/eduardtomasek/agent-code-intel/compare/v5.1.0...v6.0.0
[5.1.0]: https://github.com/eduardtomasek/agent-code-intel/compare/v5.0.0...v5.1.0
[5.0.0]: https://github.com/eduardtomasek/agent-code-intel/compare/v4.1.0...v5.0.0
[4.1.0]: https://github.com/eduardtomasek/agent-code-intel/compare/v4.0.0...v4.1.0
[4.0.0]: https://github.com/eduardtomasek/agent-code-intel/compare/v3.0.0...v4.0.0
[3.0.0]: https://github.com/eduardtomasek/agent-code-intel/releases/tag/v3.0.0
