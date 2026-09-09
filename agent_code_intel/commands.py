"""commands — mode orchestration and the reporter.

Holds the imperative sequences for the modes: ``status`` (table and JSON, issue
#53) and ``refresh`` (issue #54) are converted here; preview, apply and remove
are not yet (issues #55, #56). Plus the narrow, testable seams the modes share
(issue #41
§3, §6, §7; issue #51 criterion 5):

* :class:`CommandRunner` — the generic *capturing* subprocess seam for the
  converted modes (a whole run, output collected). The streaming external-stack
  probes ``status`` needs are their own seam in
  :mod:`agent_code_intel.integrations` (``commands`` sits above it and cannot
  route through this class without inverting the dependency). The
  :class:`CommandSpec` carries ``cwd`` and ``env`` explicitly; the caller owns
  the error policy.
* :class:`Reporter` — writes to the passed streams immediately, preserving the
  order of this tool's own output and any subprocess output (never buffers a
  whole run).
* :class:`Finding` / :class:`ModeOutcome` — the third error path: an expected
  state, warning or drift, carried as a value, never raised. The mode decides
  whether a finding is fatal, drift, warning or normal.

``CommandExit`` (raised to preserve the exit code of an already-streamed
subprocess) is the second of the three error paths (decision 41); ``CliError``
in :mod:`agent_code_intel.config` is the first.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import os
import subprocess
from collections.abc import Mapping
from typing import TextIO

from . import integrations, project
from .config import CliError, Config, LoadedConfig
from .project import ProjectContext


class CommandExit(Exception):
    """Carries the exit code of a subprocess whose output was already streamed
    to the user — :func:`agent_code_intel.cli.main` maps it straight to that
    code rather than to the generic error 1 (issue #48, decision 41)."""

    def __init__(self, code: int) -> None:
        super().__init__("subprocess exited %d" % code)
        self.code = code


@dataclasses.dataclass(frozen=True)
class CommandSpec:
    """A subprocess to run: the argv, and the ``cwd`` / ``env`` it runs under,
    both explicit (issue #41 §3 — no ambient state). Streaming, background
    delegation and the polling windows land with the modes that need them
    (issues #54–#56)."""

    argv: tuple[str, ...]
    cwd: str | None = None
    env: Mapping[str, str] | None = None


@dataclasses.dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class CommandRunner:
    """The single generic subprocess seam (issue #41 §3). A test double can
    record one command's argv, env and ordering without re-implementing the
    external stack; the caller owns the error policy."""

    def run(self, spec: CommandSpec) -> CommandResult:
        completed = subprocess.run(
            list(spec.argv),
            cwd=spec.cwd,
            env=dict(spec.env) if spec.env is not None else None,
            capture_output=True,
            text=True,
        )
        return CommandResult(
            tuple(spec.argv),
            completed.returncode,
            completed.stdout,
            completed.stderr,
        )


class Reporter:
    """Writes to the passed streams as it goes (issue #41 §6). ``say`` is the
    reference's ``say`` — ``%s\\n`` to stdout; ``error`` is ``die``'s wording
    without the exit."""

    def __init__(self, stdout: TextIO, stderr: TextIO) -> None:
        self._stdout = stdout
        self._stderr = stderr

    def say(self, message: str = "") -> None:
        self._stdout.write("%s\n" % message)

    def row(self, verb: str, rest: str) -> None:
        """The reference's ``row`` — ``  %-9s %s\\n`` to stdout (``9406cce``
        :135). A verb longer than nine columns is not truncated."""
        self._stdout.write("  %-9s %s\n" % (verb, rest))

    def hr(self, text: str) -> None:
        """The reference's ``hr`` — the text, then a dash rule of the same
        *byte* length (``9406cce`` :136; ``${#1}`` counts bytes under the C
        locale the tests run in)."""
        self._stdout.write("%s\n" % text)
        self._stdout.write("%s\n" % ("-" * len(text.encode("utf-8"))))

    def error(self, message: str) -> None:
        self._stderr.write("[ERROR: %s]\n" % message)

    def emit_err(self, message: str = "") -> None:
        """``say`` for stderr — ``%s\\n``. Used for a subprocess's captured
        stderr and the lines of a multi-line error block (``9406cce`` :2072,
        :2033–:2035) that are not the ``[ERROR: …]`` header itself."""
        self._stderr.write("%s\n" % message)


@dataclasses.dataclass(frozen=True)
class Finding:
    """One answered question, carried as a value (issue #41 §5). ``result`` is
    the domain outcome (``"ok"`` / ``"missing"`` / ``"drift"`` / …); ``fix`` is
    the optional remediation line."""

    result: str
    message: str
    fix: str | None = None


@dataclasses.dataclass(frozen=True)
class ModeOutcome:
    """A mode's result: the exit code and any findings it produced. Not an
    exception — exit 2 (ran, found drift) is an ordinary outcome, not an
    error (issue #41 §7)."""

    exit_code: int
    findings: tuple[Finding, ...] = ()


# ================================================================= status =====
#
# The reference's `--status` (``9406cce`` :1708–:1967). Text mode carries health
# in the exit code (0 ok / 2 drift); JSON mode always exits 0 after a successful
# build and carries health in the data (DEV-5 / JSON-2). Neither ever starts a
# service (issue #53 AC 4).
#
# The reference is two code paths — `status_one` (table) and the projects loop
# inside `status_json` — and this port keeps that shape. What is genuinely
# shared is the *probe layer*: `integrations.ws_show` / `mapped_path` /
# `model_state` / `watcher_running` and `project.grepai_config_*` /
# `legacy_refresh_is_pristine` have one implementation each, and both renderers
# call that same set, so "is the watcher running" cannot answer two ways. The
# per-project identity resolution is shared too (`_identity_names`); only the
# rendering of the answers — table rows vs a JSON object — differs.


def run_status(
    *,
    as_json: bool,
    status_all: bool,
    agent_target: str,
    context: ProjectContext,
    loaded: LoadedConfig,
    conf_dir: str,
    version: str,
    stdout: TextIO,
    stderr: TextIO,
    stack: "integrations.Stack | None" = None,
) -> int:
    """Entry point for the ``status`` mode — text table or JSON.

    ``stack`` is injectable so a unit test can drive every probe with no real
    external tool installed; production passes ``None`` and one is built from
    the run's child environment.
    """

    reporter = Reporter(stdout, stderr)
    if stack is None:
        stack = integrations.Stack(loaded.child_env)
    config = loaded.config
    registry_path = loaded.conf_paths.get("REGISTRY") or os.path.join(
        conf_dir, "projects"
    )

    # The Project / Workspace / Agents header (``9406cce`` :2210–:2215) —
    # suppressed by --json in every mode (RT-9 / DEV-8).
    if not as_json:
        reporter.say("Project:   %s" % context.root)
        reporter.say("Workspace: %s" % context.workspace)
        reporter.say("Agents:    %s" % agent_target)
        reporter.say("")

    if as_json:
        _status_json(
            stdout, config, registry_path, _meta_config_file(loaded), version, stack
        )
        return 0
    return _status_text(reporter, context, status_all, registry_path, config, stack)


def _identity_names(
    root: str, identity: "project.Identity", registry_workspace: str
) -> tuple[str, str]:
    """``(workspace, proj_name)`` for a non-ERR identity: ``.code-intel`` wins
    over the registry's own workspace, and ``PROJ_NAME`` is always the file's
    (or the basename when ABSENT) — the reference's ``:1730``–``:1733`` /
    ``:1869``–``:1872``, identical in both renderers."""

    if identity.status == "OK":
        return (
            identity.workspace or registry_workspace,
            identity.project or os.path.basename(root),
        )
    if identity.status == "ABSENT":
        return registry_workspace, os.path.basename(root)
    # pragma: no cover - read_code_intel only returns OK / ABSENT / ERR, and ERR
    # is handled by each caller before this point (the reference `die`s here).
    raise CliError(
        "internal error: read_code_intel(%s) returned unexpected status '%s'"
        % (root, identity.status)
    )


def _meta_config_file(loaded: LoadedConfig) -> str:
    """What ``meta.config_file`` reports. The reference prints ``$CONF_FILE``
    (the post-source shell var); for a ``defaults.env`` run that is exactly the
    harvested ``CONF_FILE``. With TOML or no file at all the port reports the
    ``defaults.toml`` path — the approved env-lane divergence (issue #37 §7,
    ledger CFG-1)."""

    if loaded.source == "env":
        return loaded.conf_paths.get("CONF_FILE", loaded.config_file)
    return loaded.config_file


# ---------------------------------------------------------------- text table --


def _status_text(
    reporter: Reporter,
    context: ProjectContext,
    status_all: bool,
    registry_path: str,
    config: Config,
    stack: integrations.Stack,
) -> int:
    drift = False
    if status_all:
        reporter.hr("code-intel status — all registered projects")
        rows = project.read_registry(registry_path)
        if not rows:
            reporter.say("registry is empty (%s)" % registry_path)
            return 0
        for workspace, path in rows:
            drift |= _status_one(reporter, workspace, path, config, stack)
    else:
        reporter.hr("code-intel status — %s" % context.root)
        drift = _status_one(
            reporter, context.workspace, context.root, config, stack
        )

    reporter.say("")
    if not drift:
        reporter.say("All good.")
        return 0
    reporter.say("Repair a project with:  agent-code-intel --path <dir> --apply")
    return 2


def _status_one(
    reporter: Reporter,
    workspace: str,
    path: str,
    config: Config,
    stack: integrations.Stack,
) -> bool:
    """One project's table rows; returns whether it contributed drift
    (``9406cce`` :1710–:1771).

    ``.code-intel`` outranks the registry's own workspace; a broken file is a
    ``BROKEN`` row, never a ``die`` — this also runs inside the ``--all`` loop,
    where one broken project must not hide every other.
    """

    root = project.canon(path)
    identity = project.read_code_intel(root)

    if identity.status == "ERR":
        reporter.row("BROKEN", "%s  %s" % (workspace, path))
        reporter.row("", "  %s" % identity.message)
        return True

    workspace, proj_name = _identity_names(root, identity, workspace)
    grepai_cfg = os.path.join(path, ".grepai", "config.yaml")
    refresh_script = os.path.join(path, "refresh-intel.sh")

    if not os.path.isdir(path):
        reporter.row(
            "GONE", "%s  %s  (directory no longer exists)" % (workspace, path)
        )
        return True

    show = stack.ws_show(workspace)
    mapped = integrations.mapped_path(show, proj_name)
    maps_here = bool(mapped) and project.canon(mapped) == root

    if mapped and not maps_here:
        reporter.row("CONFLICT", "%s  %s" % (workspace, path))
        reporter.row("", "  '%s' is mapped to %s, not here" % (proj_name, mapped))
        reporter.row(
            "",
            "  fix: grepai workspace remove %s %s && agent-code-intel %s "
            "--path %s --apply" % (workspace, proj_name, workspace, root),
        )
        return True

    bad = False
    if not stack.ws_exists(workspace):
        bad = True
        reporter.row("", "  workspace '%s' does not exist" % workspace)
    if not maps_here:
        bad = True
        reporter.row("", "  workspace does not map this path")
    if integrations.model_state(show, config.embed_model) == "mismatch":
        bad = True
        reporter.row("", "  embedder differs from %s" % config.embed_model)
    if not project.grepai_config_chunking_ok(
        grepai_cfg, config.chunk_size, config.chunk_overlap
    ):
        bad = True
        reporter.row(
            "", "  chunking is not %s/%s" % (config.chunk_size, config.chunk_overlap)
        )
    if not project.grepai_config_ignores_ok(grepai_cfg, config.extra_ignores):
        bad = True
        reporter.row("", "  lock files not in the ignore list")
    if not integrations.watcher_running(stack.watch_status(workspace)):
        bad = True
        reporter.row("", "  watcher not running")
    if identity.status == "ABSENT" and project.legacy_refresh_is_pristine(
        refresh_script
    ):
        bad = True
        reporter.row(
            "", "  refresh-intel.sh present — run --apply to migrate it to .code-intel"
        )
    if os.path.isfile(os.path.join(path, ".grepai", "index.gob")):
        reporter.row("", "  stale .grepai/index.gob present (rm it)")

    reporter.row("DRIFT" if bad else "ok", "%s  %s" % (workspace, path))
    return bad


# ------------------------------------------------------------- JSON document --


def _status_json(
    stdout: TextIO,
    config: Config,
    registry_path: str,
    config_file: str,
    version: str,
    stack: integrations.Stack,
) -> None:
    """Machine-readable status (``9406cce`` :1781–:1942).

    Built on the same probes as the table; reports the services too (the table
    does not — ``--status`` must stay usable on a machine where they are down);
    starts nothing. Key order, types and conditional fields mirror the
    reference exactly so ``code-intel-dash`` is unaffected (JSON-1, JSON-7).
    """

    meta: dict[str, object] = {
        "schema": "1",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "script_version": version,
        "config_file": config_file,
        "chunk_size": config.chunk_size,
        "chunk_overlap": config.chunk_overlap,
        "embed_model": config.embed_model,
        "embed_provider": config.embed_provider,
    }

    doc: dict[str, object] = {
        "meta": meta,
        "tool": _json_tools(stack),
        "svc": _json_services(config, stack),
        "projects": [],
    }
    projects = _json_projects(registry_path, config, stack)
    doc["projects"] = projects
    meta["project_count"] = str(len(projects))

    json.dump(doc, stdout, indent=2, ensure_ascii=False)
    stdout.write("\n")


def _json_tools(stack: integrations.Stack) -> dict[str, object]:
    tools: dict[str, object] = {}

    if stack.have("grepai"):
        tools["grepai"] = {
            "present": True,
            "version": stack.first_line("grepai", "version"),
        }
    else:
        tools["grepai"] = {"present": False}

    if stack.have("gitnexus"):
        gitnexus: dict[str, object] = {"present": True}
        if stack.gitnexus_runs():
            gitnexus["runs"] = True
            gitnexus["version"] = stack.first_line("gitnexus", "--version")
        else:
            gitnexus["runs"] = False
        tools["gitnexus"] = gitnexus
    else:
        tools["gitnexus"] = {"present": False}

    if stack.have("node"):
        tools["node"] = {
            "present": True,
            "version": stack.first_line("node", "--version"),
            "path": stack.which("node"),
            "register_hooks": stack.node_has_register_hooks(),
        }
    else:
        tools["node"] = {"present": False}

    tools["claude"] = {"present": stack.have("claude")}
    tools["codex"] = {"present": stack.have("codex")}
    tools["rtk"] = {"present": stack.have("rtk")}
    return tools


def _json_services(config: Config, stack: integrations.Stack) -> dict[str, object]:
    svc: dict[str, object] = {}

    cli = stack.container_cli()
    container: dict[str, object] = {"cli": cli}
    if cli and stack.container_daemon_ok(cli):
        container["daemon"] = True
        container["qdrant_state"] = stack.container_inspect(
            cli, "{{.State.Status}}", config.qdrant_container, "absent"
        )
        container["qdrant_ports"] = stack.container_inspect(
            cli, "{{json .HostConfig.PortBindings}}", config.qdrant_container, "{}"
        )
        container["qdrant_started"] = stack.container_inspect(
            cli, "{{.State.StartedAt}}", config.qdrant_container, ""
        )
    else:
        container["daemon"] = False
    container["name"] = config.qdrant_container
    svc["container"] = container

    qdrant_http = "http://%s:%s" % (config.qdrant_host, config.qdrant_http_port)
    svc["qdrant"] = {
        "http_url": qdrant_http,
        "grpc_port": config.qdrant_port,
        "http": stack.qdrant_http_ok(qdrant_http),
        "grpc": stack.qdrant_grpc_ok(config.qdrant_host, config.qdrant_port),
    }

    ollama: dict[str, object] = {"endpoint": config.ollama_http}
    if stack.have("ollama"):
        ollama["present"] = True
        if stack.ollama_up():
            ollama["up"] = True
            ollama["model_present"] = stack.ollama_has_model(config.embed_model)
        else:
            ollama["up"] = False
    else:
        ollama["present"] = False
    svc["ollama"] = ollama
    return svc


def _json_projects(
    registry_path: str, config: Config, stack: integrations.Stack
) -> list[dict[str, object]]:
    projects: list[dict[str, object]] = []

    for workspace, registered_path in project.read_registry(registry_path):
        root = project.canon(registered_path)
        identity = project.read_code_intel(root)
        entry: dict[str, object] = {}

        if identity.status == "ERR":
            entry["workspace"] = workspace
            entry["path"] = root
            entry["code_intel_error"] = identity.message
            entry["ok"] = False
            projects.append(entry)
            continue

        workspace, proj_name = _identity_names(root, identity, workspace)

        grepai_cfg = os.path.join(root, ".grepai", "config.yaml")
        refresh_script = os.path.join(root, "refresh-intel.sh")
        bad = False

        entry["workspace"] = workspace
        entry["path"] = root
        entry["name"] = proj_name

        if not os.path.isdir(root):
            entry["exists"] = False
            entry["ok"] = False
            projects.append(entry)
            continue
        entry["exists"] = True

        show = stack.ws_show(workspace)

        if stack.ws_exists(workspace):
            entry["workspace_exists"] = True
        else:
            entry["workspace_exists"] = False
            bad = True

        mapped = integrations.mapped_path(show, proj_name)
        maps_here = bool(mapped) and project.canon(mapped) == root
        entry["mapped"] = maps_here
        if not maps_here:
            bad = True
        entry["mapped_path"] = mapped

        state = integrations.model_state(show, config.embed_model)
        entry["embedder"] = state
        if state == "mismatch":
            bad = True

        if project.grepai_config_chunking_ok(
            grepai_cfg, config.chunk_size, config.chunk_overlap
        ):
            entry["chunking_ok"] = True
        else:
            entry["chunking_ok"] = False
            bad = True

        if project.grepai_config_ignores_ok(grepai_cfg, config.extra_ignores):
            entry["ignores_ok"] = True
        else:
            entry["ignores_ok"] = False
            bad = True

        if integrations.watcher_running(stack.watch_status(workspace)):
            entry["watcher"] = True
        else:
            entry["watcher"] = False
            bad = True

        if identity.status == "ABSENT" and project.legacy_refresh_is_pristine(
            refresh_script
        ):
            bad = True

        entry["gob_leftover"] = os.path.isfile(
            os.path.join(root, ".grepai", "index.gob")
        )
        entry["collection"] = "workspace_%s" % workspace
        entry["ok"] = not bad
        projects.append(entry)

    return projects


# ================================================================ refresh =====
#
# The reference's `--refresh` (``9406cce`` :1969–:2115): a lighter preflight than
# `preflight()` — only what this run will use, gated by --no-grepai /
# --no-gitnexus — then re-index and audit. It never founds a project: the ABSENT
# `.code-intel` case already died in `project.resolve_project` (#51), so by here
# identity is known-good (issue #54 AC 1; REF-1).
#
# Three outcomes, kept apart the way issue #41 §5/§7 asks: an unmet dependency is
# a `CliError` (exit 1, nothing refreshed); a failed re-index is *not* fatal —
# the audit still runs and the run exits 2 (AC 3; REF-5 / TOL-3); drift the audit
# finds is exit 2 too. Only a clean pass is exit 0.


@dataclasses.dataclass(frozen=True)
class _Need:
    what: str
    fix: str


def run_refresh(
    *,
    as_json: bool,
    do_grepai: bool,
    do_gitnexus: bool,
    agent_target: str,
    context: ProjectContext,
    loaded: LoadedConfig,
    stdout: TextIO,
    stderr: TextIO,
    stack: "integrations.Stack | None" = None,
) -> int:
    """Entry point for the ``refresh`` mode.

    ``stack`` is injectable so a unit test can drive the preflight, the
    re-index and the audit with no real external tool installed; production
    passes ``None`` and one is built from the run's child environment.
    """

    reporter = Reporter(stdout, stderr)
    if stack is None:
        stack = integrations.Stack(loaded.child_env)
    config = loaded.config

    # `if [[ "$AS_JSON" != true ]]` (``9406cce`` :2210) — one guard for every
    # mode's header; --refresh inherits it (DEV-8 / RT-9).
    if not as_json:
        reporter.say("Project:   %s" % context.root)
        reporter.say("Workspace: %s" % context.workspace)
        reporter.say("Agents:    %s" % agent_target)
        reporter.say("")

    _refresh_preflight(reporter, do_grepai, do_gitnexus, context, config, stack)
    return _do_refresh(reporter, do_grepai, do_gitnexus, context, config, stack)


def _refresh_preflight(
    reporter: Reporter,
    do_grepai: bool,
    do_gitnexus: bool,
    context: ProjectContext,
    config: Config,
    stack: integrations.Stack,
) -> None:
    """``refresh_preflight`` (``9406cce`` :1984–:2040). Checks only what this
    run will touch. Any unmet dependency prints the whole ``MISSING`` list, then
    a multi-line error block to stderr, and raises — exit 1, nothing refreshed
    (REF-4)."""

    reporter.hr("Preflight (--refresh)")
    needs: list[_Need] = []

    def need(what: str, fix: str) -> None:
        needs.append(_Need(what, fix))
        reporter.row("MISSING", what)

    if do_grepai:
        if stack.have("grepai"):
            reporter.row("ok", "grepai on PATH")
        else:
            need("grepai not on PATH", "install GrepAI, or re-run with --no-grepai")

        qdrant_http = "http://%s:%s" % (config.qdrant_host, config.qdrant_http_port)
        http_ok = stack.qdrant_http_ok(qdrant_http)
        # `if qdrant_http_ok && qdrant_grpc_ok` (``9406cce`` :1991) — the gRPC
        # port is only probed when HTTP already answered.
        grpc_ok = http_ok and stack.qdrant_grpc_ok(
            config.qdrant_host, config.qdrant_port
        )
        if http_ok and grpc_ok:
            reporter.row(
                "ok",
                "qdrant healthy on %s (HTTP) and %s (gRPC)"
                % (config.qdrant_http_port, config.qdrant_port),
            )
        elif http_ok:
            need(
                "qdrant answers on %s but gRPC %s is closed — grepai reads and "
                "writes vectors there"
                % (config.qdrant_http_port, config.qdrant_port),
                "republish the container with both ports",
            )
        else:
            need(
                "qdrant not healthy at %s/healthz" % qdrant_http,
                "start it, or run: agent-code-intel --path %s --apply" % context.root,
            )

        if not stack.have("ollama"):
            need(
                "ollama not on PATH",
                "install ollama — the watcher embeds every change through it",
            )
        elif not stack.ollama_up():
            need(
                "ollama server not responding at %s" % config.ollama_http,
                "start it: ollama serve",
            )
        elif not stack.ollama_has_model(config.embed_model):
            need(
                "embedding model %s not pulled" % config.embed_model,
                "ollama pull %s" % config.embed_model,
            )
        else:
            reporter.row("ok", "ollama responding, %s available" % config.embed_model)

    if do_gitnexus:
        if not stack.have("gitnexus"):
            need(
                "gitnexus not on PATH",
                "npm i -g gitnexus, or re-run with --no-gitnexus",
            )
        elif not stack.gitnexus_runs():
            need(
                "gitnexus is on PATH but does not run",
                "npm's global bin is an nvm-versioned shim that a node switch "
                "leaves broken: npm i -g gitnexus",
            )
        else:
            reporter.row(
                "ok", "gitnexus %s runs" % stack.first_line("gitnexus", "--version")
            )

        if stack.have("git"):
            reporter.row("ok", "git on PATH")
        else:
            need(
                "git not on PATH",
                "install git — GitNexus derives staleness from it",
            )

    reporter.say("")
    if not needs:
        return

    word = "dependency" if len(needs) == 1 else "dependencies"
    reporter.error(
        "refresh preflight found %d unmet %s — nothing was refreshed"
        % (len(needs), word)
    )
    reporter.emit_err("")
    for entry in needs:
        reporter.emit_err("  - %s" % entry.what)
        reporter.emit_err("    fix: %s" % entry.fix)
    # The block is already on stderr; cli.main only needs the exit code.
    raise CliError("", code=1, wrap=False)


def _do_refresh(
    reporter: Reporter,
    do_grepai: bool,
    do_gitnexus: bool,
    context: ProjectContext,
    config: Config,
    stack: integrations.Stack,
) -> int:
    """``do_refresh`` (``9406cce`` :2042–:2115). Start the watcher if it is
    down, re-index GitNexus (a failure is reported, not fatal), then audit each
    enabled side: the GrepAI audit reuses ``--status``' own ``_status_one``, and
    the GitNexus audit is a freshness check on ``gitnexus status`` that only
    ``--refresh`` does (``--status`` never re-checks the graph)."""

    reporter.hr("code-intel refresh — %s" % context.root)
    bad = False
    drift = False

    if do_grepai:
        reporter.say("")
        reporter.hr("GrepAI watcher")
        if integrations.watcher_running(stack.watch_status(context.workspace)):
            reporter.say("already running for workspace %s" % context.workspace)
        else:
            reporter.say("starting watcher for workspace %s..." % context.workspace)
            _replay(reporter, stack.watch_start_background(context.workspace))

    if do_gitnexus:
        reporter.say("")
        reporter.hr("GitNexus re-index")
        if not _reindex(reporter, stack, context):
            bad = True
            reporter.say("gitnexus analyze failed")
            if stack.have("node") and not stack.node_has_register_hooks():
                reporter.say(
                    "  node %s is too old for 'gitnexus analyze'"
                    % stack.first_line("node", "--version")
                )
                reporter.say("  fix: brew upgrade node && npm i -g gitnexus")

    reporter.say("")
    if do_grepai:
        reporter.hr("GrepAI audit")
        drift |= _status_one(
            reporter, context.workspace, context.root, config, stack
        )
        reporter.say("")

    if do_gitnexus:
        reporter.hr("GitNexus audit")
        gnout = stack.gitnexus_status(context.root)
        reporter.say(gnout.rstrip("\n"))
        if integrations.gitnexus_fresh(gnout):
            reporter.row("ok", "index up to date")
        else:
            reporter.row("DRIFT", "index not up to date")
            drift = True
        reporter.say("")

    if bad or drift:
        reporter.say("Code intelligence has drift or errors above.")
        return 2
    reporter.say("Code intelligence is fresh.")
    return 0


def _reindex(
    reporter: Reporter, stack: integrations.Stack, context: ProjectContext
) -> bool:
    """The re-index subshell (``9406cce`` :2066–:2087). ``gitnexus analyze
    --embeddings``; on the one "completed without persisted embeddings" failure,
    a structural ``--force`` retry (TOL-4); any other failure is just a failure.
    Returns whether the index is now built."""

    embeddings = stack.gitnexus_analyze_embeddings(context.root)
    merged = embeddings.stdout + embeddings.stderr
    if embeddings.returncode == 0:
        reporter.say(merged.rstrip("\n"))
        return True

    reporter.emit_err(merged.rstrip("\n"))
    if not integrations.embeddings_not_persisted(merged):
        return False

    reporter.say(
        "No GitNexus embeddings were persisted; retrying with structural indexing."
    )
    forced = stack.gitnexus_analyze_force(context.root)
    _replay(reporter, forced)
    return forced.returncode == 0


def _replay(reporter: Reporter, result: "integrations.Exec") -> None:
    """Write a captured subprocess's streams back out in stream order — the
    reference lets these commands write straight to the user."""
    if result.stdout:
        reporter.say(result.stdout.rstrip("\n"))
    if result.stderr:
        reporter.emit_err(result.stderr.rstrip("\n"))
