"""cli — argv parsing, immediate --help/--version, and mode dispatch.

This is the one entry point both launchers call: :func:`main`. It runs the
reference's fixed pipeline order (issue #41 §4): the interpreter gate (in the
launcher), then the ENV/TOML conflict check and config load, then the
hand-rolled argument loop (``9406cce`` lines 242–297) — left to right, last
mode-switch wins, no mutual-exclusivity check, ``--help`` / ``--version``
short-circuit everything to their right — then the early install branch, then
project resolution, then mode dispatch.

Parsing and early exit landed in issue #50; config load and project resolution
in issue #51. Install (#52) and the modes (#53–#56) still raise
:class:`CliError` — the port fakes no mode as working (issue #48, decision 70).
"""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Mapping
from typing import Sequence, TextIO

from . import __version__, config, project
from .config import CliError


@dataclasses.dataclass(frozen=True)
class Options:
    """The parsed command line as one immutable value (issue #48, decision 36).

    Field names and defaults mirror the reference's parser-scope globals
    (``9406cce`` lines 242–261). ``action`` is ``"run"`` for a normal
    invocation, or ``"help"`` / ``"version"`` for an immediate exit.
    """

    action: str = "run"
    mode: str = "init"
    root: str = ""
    root_explicit: bool = False
    workspace: str | None = None
    workspace_explicit: bool = False
    agent_target: str = "both"
    apply: bool = False
    bootstrap: bool = True
    do_git: bool = True
    start_watch: bool = True
    run_analyze: bool = True
    write_docs: bool = True
    force_docs: bool = False
    status_all: bool = False
    as_json: bool = False
    purge_collection: bool = False
    write_perms: bool = True
    do_grepai: bool = True
    do_gitnexus: bool = True


# Character-for-character the reference's ``usage()`` heredoc (``9406cce`` lines
# 168–238). The help text is a binding part of the contract (issue #48,
# decision 6) — do not reflow, retitle or "tidy" it.
USAGE = """\
Usage:
  agent-code-intel [workspace] [--path DIR] [options]        preview
  agent-code-intel [workspace] [--path DIR] --apply          set up / repair
  agent-code-intel --refresh [--path DIR]                    re-index + audit
  agent-code-intel --status [--all]                          health check
  agent-code-intel --status --all --json                     machine-readable
  agent-code-intel --remove [--apply] [--path DIR]           tear out
  agent-code-intel --install                                 self-install

Preview exit codes:   0 = everything matches, 2 = drift, 1 = error.
--refresh exit codes: 0 = ok, 1 = could not run (missing deps, or this
                      project has no .code-intel yet -- run --apply first),
                      2 = ran, but found drift or a stale index.

Options:
  --apply           Actually make changes. Without it: preview only.
  --refresh         Re-index GitNexus, start the GrepAI watcher if it is not
                    running, then audit — like --status, plus those writes.
                    Never creates anything: fails if .code-intel is missing.
                    Root is the enclosing git repo (--path overrides this).
  --path DIR        Project directory (default: current directory). With
                    --refresh: an explicit override that skips the git-root
                    search below.
  --agent WHO       claude | codex | both        (default: both)
  --no-bootstrap    Do not start qdrant / ollama; only check them
  --no-git          Do not run `git init` or touch .gitignore
  --no-watch        Do not start the GrepAI watcher
  --no-analyze      Skip the initial GitNexus analyze (slow on big repos)
  --no-docs         Do not touch CLAUDE.md / AGENTS.md
  --force-docs      Rewrite the code-intel block even if one is present
  --no-grepai       With --refresh: skip the GrepAI watcher check/start
  --no-gitnexus     With --refresh: skip the GitNexus re-index
  --all             With --status: every project in the registry
  --json            With --status: emit JSON instead of a table. Reports the
                    services too (container runtime, qdrant, ollama, node) and
                    never starts anything. Feeds code-intel-dash.
  --purge-collection  With --remove: also delete the qdrant collection
  --no-perms        With --install: do not touch ~/.claude/settings.json
  -h, --help        This text
  --version         Print version

Config: ~/.config/code-intel/defaults.env (sourced if present) overrides
chunk size, embedding model, ports and container names.

ABOUT THIS TOOL, AND WHY --refresh MIGHT FAIL
    This is a LOCAL DEVELOPER TOOL. It is not part of any project's build,
    test suite or CI, and no application code depends on it. It keeps two
    code-search indexes fresh so AI coding agents can navigate a repository:
    a GitNexus knowledge graph and a GrepAI semantic index.

    It needs a stack that is NOT part of any project it wires up, and that
    `npm install` does not provide: the `grepai` and `gitnexus` CLIs, a
    running qdrant (HTTP and gRPC), and a running ollama with one embedding
    model pulled.

    `--refresh` checks for all of that before touching anything. On a
    machine that never installed this stack, either the `agent-code-intel`
    command itself is not found, or it runs and its preflight exits 1
    listing what is missing. Both are EXPECTED AND HARMLESS: the failure
    says nothing about the health of the project's code. Do NOT "fix" the
    repository in response to it, and do NOT add these services to a
    project's dependencies, CI or docker-compose.

    If a CLAUDE.md / AGENTS.md here tells an agent to run `agent-code-intel
    --refresh` after every task that changes code: that instruction assumes
    this stack is installed. If it fails, skip it, say so plainly in the
    summary, and get on with the real task — these indexes are a
    navigation convenience, never a correctness gate.

    To remove it from a project entirely: `agent-code-intel --remove --apply`
    there.
"""

# Bare boolean switches: flag → the Options field it sets, and the value it
# sets it to. Order and spelling are the reference's (``9406cce`` 275–290).
_BOOL_FLAGS = {
    "--apply": ("apply", True),
    "--all": ("status_all", True),
    "--json": ("as_json", True),
    "--no-bootstrap": ("bootstrap", False),
    "--no-git": ("do_git", False),
    "--no-watch": ("start_watch", False),
    "--no-analyze": ("run_analyze", False),
    "--no-docs": ("write_docs", False),
    "--force-docs": ("force_docs", True),
    "--no-grepai": ("do_grepai", False),
    "--no-gitnexus": ("do_gitnexus", False),
    "--purge-collection": ("purge_collection", True),
    "--no-perms": ("write_perms", False),
}

# Mode-switch flags: flag → mode. "Last one wins" (decision 5); there is no
# check that only one was given.
_MODE_FLAGS = {
    "--refresh": "refresh",
    "--status": "status",
    "--remove": "remove",
    "--install": "install",
}


def parse_args(argv: Sequence[str], default_root: str) -> Options:
    """Reproduce the reference's argument loop.

    Returns an :class:`Options`. ``--help`` / ``--version`` return immediately
    with ``action`` set and everything to their right unread. Any parse error
    raises :class:`CliError` with the reference's exact wording.
    """

    fields: dict[str, object] = {"root": default_root}
    args = list(argv)
    i = 0
    while i < len(args):
        arg = args[i]

        if arg == "--path":
            if i + 1 >= len(args):
                raise CliError("--path requires a directory argument")
            fields["root"] = args[i + 1]
            fields["root_explicit"] = True
            i += 2
            continue

        if arg == "--agent":
            if i + 1 >= len(args):
                raise CliError("--agent requires: claude, codex or both")
            value = args[i + 1]
            if value not in ("claude", "codex", "both"):
                raise CliError(
                    "--agent must be claude, codex or both (got '%s')" % value
                )
            fields["agent_target"] = value
            i += 2
            continue

        if arg in _MODE_FLAGS:
            fields["mode"] = _MODE_FLAGS[arg]
            i += 1
            continue

        if arg in _BOOL_FLAGS:
            name, value = _BOOL_FLAGS[arg]
            fields[name] = value
            i += 1
            continue

        if arg == "--version":
            return Options(action="version", **fields)

        if arg in ("-h", "--help"):
            return Options(action="help", **fields)

        if arg.startswith("-"):
            raise CliError("unknown flag: %s" % arg)

        # Positional: the workspace name. The reference guards on emptiness
        # (``[[ -z "$WS" ]]``), not on whether one was already seen — an
        # explicit "" does not count as taken.
        if fields.get("workspace"):
            raise CliError(
                "workspace name given twice ('%s' and '%s')"
                % (fields["workspace"], arg)
            )
        fields["workspace"] = arg
        fields["workspace_explicit"] = True
        i += 1

    return Options(**fields)


def main(
    argv: Sequence[str],
    env: Mapping[str, str],
    cwd: str,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """The single launcher entry point (issue #48, decision 35).

    ``env`` is the process environment; ``config.load`` reads the XDG config
    location from it and hands every subprocess a
    :class:`~agent_code_intel.config.ChildEnvironment` derived from it — the
    global ``os.environ`` is never mutated.
    """

    try:
        environ = dict(env)

        # Pipeline order (issue #41 §4): ENV/TOML conflict check + config load
        # run *before* argument parsing, so a config error kills --help and
        # --version exactly as the reference's `. "$CONF_FILE"` on :126 does.
        # The Config / ChildEnvironment it returns are consumed once a mode is
        # converted (#53+); here the load matters for its validation.
        config.load(_conf_dir(environ), environ, cwd)

        opts = parse_args(argv, default_root=cwd)

        if opts.action == "version":
            stdout.write("agent-code-intel %s\n" % __version__)
            return 0
        if opts.action == "help":
            stdout.write(USAGE)
            return 0

        if opts.mode == "install":
            raise CliError(
                "the Python port does not implement the 'install' mode yet "
                "(issue #52)"
            )

        project.resolve_project(
            root=opts.root,
            root_explicit=opts.root_explicit,
            mode=opts.mode,
            workspace=opts.workspace,
            home=_home(environ),
            status_all=opts.status_all,
        )

        # Config load and identity resolution are converted; the modes
        # themselves are not — say so plainly rather than exit 0 on a mode
        # that does nothing (issue #48, decision 70).
        label = "status-json" if opts.mode == "status" and opts.as_json else opts.mode
        raise CliError(
            "the Python port does not implement the '%s' mode yet "
            "(issues #53–#56)" % label
        )
    except CliError as exc:
        if exc.wrap:
            stderr.write("[ERROR: %s]\n" % exc)
        else:
            stderr.write(str(exc))
        return exc.code


def _home(environ: Mapping[str, str]) -> str:
    return environ.get("HOME") or os.path.expanduser("~")


def _conf_dir(environ: Mapping[str, str]) -> str:
    """``${XDG_CONFIG_HOME:-$HOME/.config}/code-intel`` (``9406cce`` :121).

    An empty ``XDG_CONFIG_HOME`` falls through to the default, matching the
    shell's ``:-`` form.
    """

    xdg = environ.get("XDG_CONFIG_HOME")
    base = xdg if xdg else os.path.join(_home(environ), ".config")
    return os.path.join(base, "code-intel")
