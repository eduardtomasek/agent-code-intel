"""commands — mode orchestration and the reporter.

Holds the imperative sequences for the modes: ``status`` (table and JSON, issue
#53), ``refresh`` (issue #54), preview/apply (issue #55) and remove (issue #56)
are converted here. Plus the narrow, testable seams the modes share
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
import re
import shutil
import subprocess
import time
from collections.abc import Mapping
from typing import TextIO

from . import agent_skills, integrations, project
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


# ================================================================ init ========
#
# Preview and apply intentionally remain separate imperative paths. They share
# probes and file transforms, but apply keeps the reference's non-atomic order
# so a failure after `.code-intel` is visible rather than silently rolled back.


@dataclasses.dataclass(frozen=True)
class _Need:
    what: str
    fix: str


_DOC_BLOCKS = {
    "CLAUDE.md": """<!-- code-intel:start -->
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
<!-- code-intel:end -->""",
    "AGENTS.md": """<!-- code-intel:start -->
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
<!-- code-intel:end -->""",
}


def run_init(
    *,
    apply: bool,
    bootstrap: bool,
    do_git: bool,
    start_watch: bool,
    run_analyze: bool,
    write_docs: bool,
    force_docs: bool,
    agent_target: str,
    context: ProjectContext,
    loaded: LoadedConfig,
    conf_dir: str,
    stdout: TextIO,
    stderr: TextIO,
    stack: "integrations.Stack | None" = None,
) -> int:
    """Run the initial project setup in preview or apply mode."""

    reporter = Reporter(stdout, stderr)
    if stack is None:
        stack = integrations.Stack(loaded.child_env)
    config = loaded.config
    context = _adopt_preview_context(context)
    reporter.say("Project:   %s" % context.root)
    reporter.say("Workspace: %s" % context.workspace)
    reporter.say("Agents:    %s" % agent_target)
    reporter.say("")
    _init_preflight(
        reporter,
        bootstrap,
        agent_target,
        context,
        config,
        stack,
    )
    if apply and write_docs:
        agent_skills.validate_targets(context.root, agent_target, force_docs)
    if apply:
        return _apply_init(
            reporter,
            do_git,
            start_watch,
            run_analyze,
            write_docs,
            force_docs,
            agent_target,
            context,
            config,
            loaded,
            conf_dir,
            stack,
        )
    return _preview_init(
        reporter,
        do_git,
        start_watch,
        run_analyze,
        write_docs,
        force_docs,
        agent_target,
        context,
        config,
        loaded,
        stack,
    )


def _adopt_preview_context(context: ProjectContext) -> ProjectContext:
    """Use a pristine legacy workspace for preview without writing anything."""
    if context.workspace_explicit or context.ident_status != "ABSENT" or not project.legacy_refresh_is_pristine(
        context.refresh_script
    ):
        return context
    legacy = project.read_legacy_workspace(context.refresh_script)
    if not legacy or context.ident_workspace == legacy:
        return context
    return dataclasses.replace(context, workspace=legacy)


def _init_preflight(
    reporter: Reporter,
    bootstrap: bool,
    agent_target: str,
    context: ProjectContext,
    config: Config,
    stack: integrations.Stack,
) -> None:
    reporter.hr("Preflight")
    needs: list[_Need] = []
    reporter.row("ok", "python3 on PATH")

    def need(what: str, fix: str) -> None:
        needs.append(_Need(what, fix))
        reporter.row("MISSING", what)

    if stack.have("grepai"):
        reporter.row("ok", "grepai on PATH")
    else:
        need("grepai not on PATH", "install GrepAI — it owns the workspace, watcher and search")

    if stack.have("gitnexus"):
        if stack.gitnexus_runs():
            reporter.row("ok", "gitnexus %s runs" % stack.first_line("gitnexus", "--version"))
            if stack.have("node") and not stack.node_has_register_hooks():
                reporter.row("warn", "node %s is too old for 'gitnexus analyze'" % stack.first_line("node", "--version"))
        else:
            need(
                "gitnexus is on PATH but does not run",
                "npm's global bin is an nvm-versioned shim that a node switch leaves broken: npm i -g gitnexus",
            )
    else:
        need("gitnexus not on PATH", "npm i -g gitnexus")

    if stack.have("curl"):
        reporter.row("ok", "curl on PATH")
    else:
        need("curl not on PATH", "install curl — qdrant health checks")
    if stack.have("git"):
        reporter.row("ok", "git on PATH")
    else:
        need("git not on PATH", "install git — GitNexus derives staleness from it")
    if agent_target in ("claude", "both"):
        if stack.have("claude"):
            reporter.row("ok", "claude on PATH")
        else:
            need("claude not on PATH", "install Claude Code, or use --agent codex")
    if agent_target in ("codex", "both"):
        if stack.have("codex"):
            reporter.row("ok", "codex on PATH")
        else:
            need("codex not on PATH", "install Codex, or use --agent claude")

    http_url = "http://%s:%s" % (config.qdrant_host, config.qdrant_http_port)
    http_ok = stack.qdrant_http_ok(http_url)
    grpc_ok = http_ok and stack.qdrant_grpc_ok(config.qdrant_host, config.qdrant_port)
    if http_ok and grpc_ok:
        reporter.row("ok", "qdrant healthy on %s (HTTP) and %s (gRPC)" % (config.qdrant_http_port, config.qdrant_port))
    elif _ensure_qdrant(reporter, bootstrap, context, config, stack):
        reporter.row("ok", "qdrant started and healthy on %s and %s" % (config.qdrant_http_port, config.qdrant_port))
    elif http_ok:
        need(
            "qdrant answers on %s but gRPC %s is closed — grepai reads and writes vectors there" % (config.qdrant_http_port, config.qdrant_port),
            "republish the container with both ports (see below)",
        )
    elif not stack.container_cli():
        need(
            "qdrant not reachable at %s and no container runtime found" % http_url,
            "install Docker Desktop / OrbStack / podman, or run qdrant yourself on %s and %s" % (config.qdrant_http_port, config.qdrant_port),
        )
    else:
        cli = stack.container_cli()
        if not stack.container_daemon_ok(cli):
            need(
                "%s is installed but its daemon is not running — that is why qdrant could not be started" % cli,
                "start Docker Desktop or OrbStack, wait for it to come up, then re-run this command",
            )
        else:
            need(
                "qdrant not reachable at %s" % http_url,
                "%s run -d --name %s -p %s:6333 -p %s:6334 -v %s:/qdrant/storage %s" % (cli, config.qdrant_container, config.qdrant_http_port, config.qdrant_port, config.qdrant_volume, config.qdrant_image),
            )

    if not stack.have("ollama"):
        need("ollama not on PATH", "install ollama — it serves %s on every index" % config.embed_model)
    elif _ensure_ollama(reporter, bootstrap, config, stack):
        if _ensure_model(reporter, bootstrap, config, stack):
            reporter.row("ok", "embedding model %s available" % config.embed_model)
        else:
            need("embedding model %s not pulled" % config.embed_model, "ollama pull %s" % config.embed_model)
    else:
        need("ollama server not responding at %s" % config.ollama_http, "start it: ollama serve")

    reporter.say("")
    if needs:
        word = "dependency" if len(needs) == 1 else "dependencies"
        reporter.error("preflight found %d unmet %s — nothing was changed" % (len(needs), word))
        reporter.emit_err("")
        for entry in needs:
            reporter.emit_err("  - %s" % entry.what)
            reporter.emit_err("    fix: %s" % entry.fix)
        reporter.emit_err("")
        reporter.emit_err("All of it is needed by agent-code-intel AND by --refresh, which runs")
        reporter.emit_err("after every task that changes code.")
        raise CliError("", code=1, wrap=False)


def _ensure_qdrant(reporter, bootstrap, context, config, stack) -> bool:
    if not bootstrap:
        return False
    cli = stack.container_cli()
    if not cli or not stack.container_daemon_ok(cli):
        return False
    names = stack.container_list(cli).splitlines()
    if config.qdrant_container in names:
        ports = stack.container_inspect(cli, "{{json .HostConfig.PortBindings}}", config.qdrant_container, "{}")
        if config.qdrant_port not in ports:
            reporter.say("  container '%s' exists but does not publish %s" % (config.qdrant_container, config.qdrant_port))
            return False
        result = stack.container_start(cli, config.qdrant_container)
    else:
        result = stack.container_run(cli, config.qdrant_container, config.qdrant_http_port, config.qdrant_port, config.qdrant_volume, config.qdrant_image)
    if result.returncode != 0:
        reporter.say("  %s failed: %s" % (cli, (result.stderr or result.stdout).rstrip()))
        return False
    for _ in range(90):
        if stack.qdrant_http_ok("http://%s:%s" % (config.qdrant_host, config.qdrant_http_port)) and stack.qdrant_grpc_ok(config.qdrant_host, config.qdrant_port):
            return True
        time.sleep(1)
    return False


def _ensure_ollama(reporter, bootstrap, config, stack) -> bool:
    if stack.ollama_up():
        reporter.row("ok", "ollama responding at %s" % config.ollama_http)
        return True
    if not bootstrap:
        return False
    reporter.say("  starting ollama server...")
    if stack.ollama_serve_background().returncode != 0:
        return False
    for _ in range(30):
        if stack.ollama_up():
            reporter.row("ok", "ollama responding at %s" % config.ollama_http)
            return True
        time.sleep(1)
    return False


def _ensure_model(reporter, bootstrap, config, stack) -> bool:
    if stack.ollama_has_model(config.embed_model):
        return True
    if not bootstrap:
        return False
    reporter.say("  pulling %s (this downloads ~1 GB, once per machine)..." % config.embed_model)
    if stack.ollama_pull(config.embed_model).returncode != 0:
        return False
    for _ in range(10):
        if stack.ollama_has_model(config.embed_model):
            return True
        time.sleep(1)
    return False


def _preview_init(
    reporter,
    do_git,
    start_watch,
    run_analyze,
    write_docs,
    force_docs,
    agent_target,
    context,
    config,
    loaded,
    stack,
) -> int:
    """Print the converging plan without changing project files."""
    drift = False
    reporter.say("PREVIEW — services may be started during preflight; project changes require --apply")
    reporter.say("====================================================================================")
    reporter.say("")
    reporter.say("Would do")

    def plan(verb: str, message: str) -> None:
        nonlocal drift
        reporter.row(verb, message)
        if verb not in ("", "keep", "skip", "note"):
            drift = True

    if do_git:
        if stack.git_is_repo(context.root):
            plan("keep", "git repository present")
        else:
            plan("INIT", "git init")
        if project.gitignore_ok(os.path.join(context.root, ".gitignore"), config.gitignore_entries):
            plan("keep", ".gitignore covers the index directories")
        else:
            plan("EDIT", ".gitignore += %s" % " ".join(config.gitignore_entries))
    else:
        plan("skip", "git (--no-git)")

    legacy_workspace = None
    if context.ident_status == "ABSENT" and project.legacy_refresh_is_pristine(context.refresh_script):
        legacy_workspace = project.read_legacy_workspace(context.refresh_script)
        if context.workspace_explicit and legacy_workspace and context.workspace != legacy_workspace:
            plan("CONFLICT", "explicit workspace '%s' vs. '%s' read from refresh-intel.sh" % (context.workspace, legacy_workspace))

    if project.code_intel_present(context):
        plan("keep", ".code-intel present")
    else:
        plan("CREATE", ".code-intel (WORKSPACE=%s, PROJECT=%s)" % (context.workspace, context.proj_name))

    show = stack.ws_show(context.workspace)
    if stack.ws_exists(context.workspace):
        plan("keep", "workspace '%s' exists" % context.workspace)
        model = integrations.model_state(show, config.embed_model)
        if model == "match":
            plan("keep", "workspace embedder is %s" % config.embed_model)
        elif model == "mismatch":
            plan("MISMATCH", "workspace '%s' was created with a different embedder than %s" % (context.workspace, config.embed_model))
            plan("", "vectors from two models in one collection degrade search; delete the collection")
        else:
            plan("note", "could not read the workspace embedder from 'workspace show'")
        mapped = integrations.mapped_path(show, context.proj_name)
        if mapped and project.canon(mapped) == context.root:
            plan("keep", "project already mapped into '%s'" % context.workspace)
        elif integrations.name_taken(show, context.proj_name):
            plan("CONFLICT", "'%s' already maps a project named '%s' to %s" % (context.workspace, context.proj_name, mapped))
        else:
            plan("ADD", "map %s into workspace '%s'" % (context.root, context.workspace))
    else:
        plan("CREATE", "workspace '%s' (qdrant, %s/%s)" % (context.workspace, config.embed_provider, config.embed_model))
        plan("ADD", "map %s into workspace '%s'" % (context.root, context.workspace))

    if os.path.isfile(context.grepai_cfg):
        if project.grepai_config_chunking_ok(context.grepai_cfg, config.chunk_size, config.chunk_overlap):
            plan("keep", "chunking already %s/%s" % (config.chunk_size, config.chunk_overlap))
        else:
            plan("EDIT", "chunking -> %s/%s" % (config.chunk_size, config.chunk_overlap))
        if project.grepai_config_ignores_ok(context.grepai_cfg, config.extra_ignores):
            plan("keep", "lock files already ignored")
        else:
            plan("EDIT", "add lock files to the ignore list")
    else:
        plan("CREATE", ".grepai/config.yaml (chunking %s/%s + lock-file ignores)" % (config.chunk_size, config.chunk_overlap))

    if agent_target in ("claude", "both"):
        if _claude_grepai_ok(context.mcp_json, context.workspace):
            plan("keep", "claude: 'grepai' in .mcp.json for '%s'" % context.workspace)
        else:
            plan("ADD", "claude: 'grepai' in .mcp.json with --workspace %s" % context.workspace)
        plan("keep" if stack.claude_mcp_get("gitnexus", "user").returncode == 0 else "ADD", "claude: 'gitnexus' at user scope")
    if agent_target in ("codex", "both"):
        plan("keep" if stack.codex_mcp_get("grepai-%s" % context.workspace).returncode == 0 else "ADD", "codex: 'grepai-%s' registered" % context.workspace)
        plan("keep" if stack.codex_mcp_get("gitnexus").returncode == 0 else "ADD", "codex: 'gitnexus' registered")

    if not run_analyze:
        plan("skip", "gitnexus analyze (--no-analyze)")
    elif not project.project_has_sources(context.root):
        plan("note", "no source files yet — nothing for GitNexus to index")
    elif integrations.gitnexus_fresh(stack.gitnexus_status(context.root)):
        plan("keep", "GitNexus index up to date (analyze re-runs anyway on --apply)")
    else:
        plan("RUN", "gitnexus analyze in %s" % context.root)

    if context.ident_status == "ABSENT" and os.path.isfile(context.refresh_script):
        if project.legacy_refresh_is_pristine(context.refresh_script):
            plan("MIGRATE", "delete refresh-intel.sh (working tree change; nothing gets committed)")
        else:
            plan("BLOCKED", "refresh-intel.sh is hand-modified or unstamped — --apply will refuse to touch it")

    if write_docs:
        for name, enabled in (
            ("CLAUDE.md", agent_target in ("claude", "both")),
            ("AGENTS.md", agent_target in ("codex", "both")),
        ):
            if not enabled:
                continue
            path = os.path.join(context.root, name)
            state = project.doc_state(path)
            if state == "present" and project.managed_doc_current(
                path, _DOC_BLOCKS[name]
            ):
                plan("keep", "%s has the current code-intel block" % name)
            elif state == "present":
                plan("REWRITE", "%s code-intel block" % name)
            elif state == "orphaned":
                plan("BROKEN", "%s has unbalanced code-intel markers — fix by hand" % name)
            else:
                plan("WRITE", "%s code-intel block" % name)
        for agent, details in agent_skills.status(context.root, agent_target).items():
            skill_state = details["state"]
            relative = details["path"]
            if skill_state == "current":
                plan("keep", "%s routing skill at %s" % (agent, relative))
            elif skill_state == "missing":
                plan("WRITE", "%s routing skill at %s" % (agent, relative))
            elif skill_state == "managed-drift":
                plan("UPDATE", "%s routing skill at %s" % (agent, relative))
            elif skill_state == "foreign" and force_docs:
                plan(
                    "REPLACE",
                    "%s foreign routing skill at %s (--force-docs)"
                    % (agent, relative),
                )
            else:
                plan(
                    "CONFLICT",
                    "%s routing skill at %s is %s"
                    % (agent, relative, skill_state),
                )
    else:
        plan("skip", "agent documents and routing skills (--no-docs)")

    if start_watch:
        if integrations.watcher_running(stack.watch_status(context.workspace)):
            plan("keep", "watcher running for '%s'" % context.workspace)
        else:
            plan("START", "watcher for '%s'" % context.workspace)
    else:
        plan("skip", "watcher (--no-watch)")

    reporter.say("")
    if not drift:
        reporter.say("Everything already matches. Nothing to do.")
        return 0
    reporter.say("Nothing was changed. To do the above:")
    reporter.say("  agent-code-intel %s --path %s --agent %s --apply" % (context.workspace, context.root, agent_target))
    return 2


def _apply_init(
    reporter,
    do_git,
    start_watch,
    run_analyze,
    write_docs,
    force_docs,
    agent_target,
    context,
    config,
    loaded,
    conf_dir,
    stack,
) -> int:
    if context.ident_status == "ABSENT" and os.path.isfile(context.refresh_script):
        if not project.legacy_refresh_is_pristine(context.refresh_script):
            reporter.emit_err("[ERROR: %s is hand-modified (or missing its version stamp) — refusing to touch it]" % context.refresh_script)
            reporter.emit_err("")
            reporter.emit_err("Deleting someone's manual edits is the one irreversible mistake this tool")
            reporter.emit_err("can make, so migration stops here instead of guessing. Nothing was changed.")
            reporter.emit_err("To continue:")
            reporter.emit_err("")
            reporter.emit_err("  rm refresh-intel.sh && agent-code-intel --apply")
            raise CliError("", code=1, wrap=False)
        legacy = project.adopt_legacy_workspace(
            context.workspace,
            context.workspace_explicit,
            project.read_legacy_workspace(context.refresh_script),
            context.refresh_script,
        )
        try:
            os.unlink(context.refresh_script)
        except OSError as exc:
            raise CliError("could not migrate %s: %s" % (context.refresh_script, exc))
        reporter.say("Legacy migration")
        reporter.say("deleted %s, adopted WORKSPACE=%s from it" % (context.refresh_script, legacy))
        context = dataclasses.replace(context, workspace=legacy)
        if os.path.isfile(context.grepai_cfg):
            text = open(context.grepai_cfg, encoding="utf-8").read()
            updated = re.sub(r"^[ \t]+- refresh-intel\.sh[ \t]*\n", "", text, flags=re.M)
            if updated != text:
                with open(context.grepai_cfg, "w", encoding="utf-8") as handle:
                    handle.write(updated)
                if integrations.watcher_running(stack.watch_status(context.workspace)):
                    _require_success(stack.watch_stop(context.workspace), "grepai watch --stop")
                    _require_success(stack.watch_start_background(context.workspace), "grepai watch --background")
                    reporter.say("restarted the watcher so it reloads the config")
        reporter.say("")

    reporter.hr("0. Repository")
    if do_git:
        if stack.git_is_repo(context.root):
            reporter.say("git repository already present")
        else:
            result = stack.git_init(context.root)
            if result.returncode != 0:
                raise CliError("git init failed: %s" % (result.stderr or result.stdout).rstrip())
            reporter.say("git init")
        _ensure_gitignore(reporter, context.root, config.gitignore_entries)
    else:
        reporter.say("skipped git (--no-git)")

    identity_path = os.path.join(context.root, ".code-intel")
    if project.code_intel_present(context):
        reporter.say(".code-intel already present")
    else:
        with open(identity_path, "w", encoding="utf-8") as handle:
            handle.write("# agent-code-intel — identity of this repository. Generated, do not edit by hand.\nSCHEMA=1\nWORKSPACE=%s\nPROJECT=%s\n" % (context.workspace, context.proj_name))
        reporter.say("wrote .code-intel")
    reporter.say("")

    reporter.hr("1. GrepAI workspace")
    show = stack.ws_show(context.workspace)
    if stack.ws_exists(context.workspace):
        model = integrations.model_state(show, config.embed_model)
        if model == "mismatch":
            reporter.emit_err("[ERROR: workspace '%s' uses a different embedder than %s]" % (context.workspace, config.embed_model))
            reporter.emit_err("")
            reporter.emit_err("Vectors from two models in one collection silently degrade search, and")
            reporter.emit_err("re-running this cannot fix it. Either set EMBED_MODEL back in")
            reporter.emit_err("  %s" % loaded.config_file)
            reporter.emit_err("or drop the collection and re-index:")
            reporter.emit_err("  grepai workspace delete %s" % context.workspace)
            reporter.emit_err("  agent-code-intel %s --path %s --apply" % (context.workspace, context.root))
            raise CliError("", code=1, wrap=False)
        reporter.say("workspace '%s' exists" % context.workspace)
    else:
        result = stack.workspace_create(context.workspace, "http://%s" % config.qdrant_host, config.qdrant_port, config.embed_provider, config.embed_model)
        _require_success(result, "grepai workspace create")
        reporter.say("created workspace '%s'" % context.workspace)
    reporter.say("")

    reporter.hr("2. Project mapping")
    show = stack.ws_show(context.workspace)
    mapped = integrations.mapped_path(show, context.proj_name)
    if mapped and project.canon(mapped) == context.root:
        reporter.say("project already mapped into '%s'" % context.workspace)
    elif integrations.name_taken(show, context.proj_name):
        reporter.emit_err("[ERROR: workspace '%s' already maps a project named '%s' elsewhere]" % (context.workspace, context.proj_name))
        reporter.emit_err("")
        reporter.emit_err("  wanted: %s" % context.root)
        reporter.emit_err("  mapped: %s" % mapped)
        reporter.emit_err("")
        reporter.emit_err("grepai keys projects by name, so the entry cannot be repointed in place.")
        reporter.emit_err("Nothing was changed. To repair:")
        reporter.emit_err("")
        reporter.emit_err("  grepai workspace remove %s %s" % (context.workspace, context.proj_name))
        reporter.emit_err("  agent-code-intel %s --path %s --apply" % (context.workspace, context.root))
        raise CliError("", code=1, wrap=False)
    else:
        _require_success(stack.workspace_add(context.workspace, context.root), "grepai workspace add")
        reporter.say("added %s to '%s'" % (context.root, context.workspace))
    registry_path = loaded.conf_paths.get("REGISTRY") or os.path.join(conf_dir, "projects")
    project.registry_add(registry_path, context.workspace, context.root)
    reporter.say("")

    reporter.hr("3. Chunking + ignore config")
    before = None
    if os.path.isfile(context.grepai_cfg):
        before = open(context.grepai_cfg, encoding="utf-8").read()
    else:
        _require_success(stack.grepai_init(context.root, config.embed_provider, config.embed_model), "grepai init")
        reporter.say("created %s" % context.grepai_cfg)
    if os.path.isfile(context.grepai_cfg):
        try:
            updated, changed = project.update_grepai_config(context.grepai_cfg, config.chunk_size, config.chunk_overlap, config.extra_ignores)
        except ValueError as exc:
            raise CliError(str(exc))
        if changed:
            with open(context.grepai_cfg, "w", encoding="utf-8") as handle:
                handle.write(updated)
            reporter.say("updated chunking and ignore list")
        if before != updated and integrations.watcher_running(stack.watch_status(context.workspace)):
            _require_success(stack.watch_stop(context.workspace), "grepai watch --stop")
            _require_success(stack.watch_start_background(context.workspace), "grepai watch --background")
            reporter.say("restarted the watcher so it reloads the config")
    reporter.say("")

    reporter.hr("4. GrepAI MCP registration")
    if agent_target in ("claude", "both") and not _claude_grepai_ok(context.mcp_json, context.workspace):
        _require_success(stack.claude_mcp_add(context.root, "grepai", "project", ("grepai", "mcp-serve", "--workspace", context.workspace)), "claude mcp add grepai")
        reporter.say("claude: registered 'grepai' in %s with --workspace %s" % (context.mcp_json, context.workspace))
    if agent_target in ("codex", "both") and stack.codex_mcp_get("grepai-%s" % context.workspace).returncode != 0:
        _require_success(stack.codex_mcp_add("grepai-%s" % context.workspace, ("grepai", "mcp-serve", "--workspace", context.workspace)), "codex mcp add grepai")
        reporter.say("codex: registered 'grepai-%s' with --workspace %s" % (context.workspace, context.workspace))
    reporter.say("")

    reporter.hr("5. GitNexus MCP registration (global, serves every indexed repo)")
    if agent_target in ("claude", "both") and stack.claude_mcp_get("gitnexus", "user").returncode != 0:
        _require_success(stack.claude_mcp_add(context.root, "gitnexus", "user", ("gitnexus", "mcp")), "claude mcp add gitnexus")
        reporter.say("claude: registered 'gitnexus' at user scope")
    if agent_target in ("codex", "both") and stack.codex_mcp_get("gitnexus").returncode != 0:
        _require_success(stack.codex_mcp_add("gitnexus", ("gitnexus", "mcp")), "codex mcp add gitnexus")
        reporter.say("codex: registered 'gitnexus'")
    reporter.say("")

    reporter.hr("6. GitNexus index")
    analyze_result = "ok"
    if not run_analyze:
        analyze_result = "skipped"
        reporter.say("skipped (--no-analyze)")
    elif not project.project_has_sources(context.root):
        analyze_result = "empty"
        reporter.say("no source files yet — nothing to index.")
    elif not _reindex(reporter, stack, context):
        analyze_result = "failed"
        reporter.say("WARNING: gitnexus analyze failed. Setup continues — the knowledge graph is simply empty until it succeeds.")
    reporter.say("")

    reporter.hr("7. Agent instructions")
    if write_docs:
        if agent_target in ("claude", "both"):
            _write_doc(reporter, os.path.join(context.root, "CLAUDE.md"), force_docs)
        if agent_target in ("codex", "both"):
            _write_doc(reporter, os.path.join(context.root, "AGENTS.md"), force_docs)
        for agent, outcome in agent_skills.install_targets(
            context.root, agent_target, force_docs
        ):
            reporter.say(
                "%s: routing skill %s at %s"
                % (agent, outcome, agent_skills.relative_path(agent))
            )
    else:
        reporter.say("skipped agent documents and routing skills (--no-docs)")
    reporter.say("")

    if start_watch:
        reporter.hr("8. GrepAI watcher")
        if integrations.watcher_running(stack.watch_status(context.workspace)):
            reporter.say("watcher already running for '%s'" % context.workspace)
        else:
            result = stack.watch_start_background(context.workspace)
            _replay(reporter, result)
            _require_success(result, "grepai watch --background")
            reporter.say("started watcher for '%s'" % context.workspace)
        reporter.say("")
    reporter.hr("Result")
    reporter.say("Done.")
    reporter.say("- Run agent-code-intel --refresh after each task that changes the codebase.")
    if analyze_result == "failed":
        reporter.say("- GitNexus indexing FAILED — the graph is empty. Everything else is wired.")
    elif analyze_result == "skipped":
        reporter.say("- GitNexus was not indexed (--no-analyze). Run agent-code-intel --refresh to do it.")
    return 0


def _ensure_gitignore(reporter, root: str, entries: tuple[str, ...]) -> None:
    path = os.path.join(root, ".gitignore")
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        text = ""
    missing = [entry for entry in entries if entry not in text.splitlines()]
    if missing:
        if text and not text.endswith("\n"):
            text += "\n"
        text += "".join(entry + "\n" for entry in missing)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        reporter.say(".gitignore += %s" % " ".join(missing))
    else:
        reporter.say(".gitignore already covers the index directories")


def _claude_grepai_ok(path: str, workspace: str) -> bool:
    try:
        with open(path, encoding="utf-8") as handle:
            config = json.load(handle)
    except (OSError, ValueError):
        return False
    server = (config.get("mcpServers") or {}).get("grepai") or {}
    args = server.get("args") or []
    return bool(server) and "--workspace" in args and workspace in args


def _write_doc(reporter, path: str, force: bool) -> None:
    name = os.path.basename(path)
    message, _ = project.write_managed_doc(path, _DOC_BLOCKS[name], force)
    if message.startswith("unbalanced code-intel markers"):
        raise CliError("%s: %s" % (path, message))
    reporter.say("%s: %s" % (os.path.basename(path), message))


def _require_success(result: "integrations.Exec", operation: str) -> None:
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).rstrip()
        raise CliError("%s failed%s" % (operation, ": %s" % detail if detail else ""))


# ================================================================ remove =====
#
# Remove deliberately has its own imperative path. It does not run the full
# preflight: a project must remain removable when GrepAI, Qdrant or the agent
# CLIs are already down. Remote failures are therefore intentionally ignored,
# while local ownership checks still decide what may be changed.


def run_remove(
    *,
    apply: bool,
    as_json: bool,
    purge_collection: bool,
    agent_target: str,
    context: ProjectContext,
    loaded: LoadedConfig,
    conf_dir: str,
    stdout: TextIO,
    stderr: TextIO,
    stack: "integrations.Stack | None" = None,
) -> int:
    """Preview or apply the safe project removal sequence (issue #56)."""
    reporter = Reporter(stdout, stderr)
    if stack is None:
        stack = integrations.Stack(loaded.child_env)
    config = loaded.config
    registry_path = loaded.conf_paths.get("REGISTRY") or os.path.join(
        conf_dir, "projects"
    )

    if not as_json:
        reporter.say("Project:   %s" % context.root)
        reporter.say("Workspace: %s" % context.workspace)
        reporter.say("Agents:    %s" % agent_target)
        reporter.say("")

    reporter.hr(
        "Remove code-intel from %s (workspace '%s')"
        % (context.root, context.workspace)
    )

    def maps_here() -> bool:
        show = stack.ws_show(context.workspace)
        mapped = integrations.mapped_path(show, context.proj_name)
        return bool(mapped) and project.canon(mapped) == context.root

    def removal_plan(verb: str) -> int:
        actions = 0
        if integrations.watcher_running(stack.watch_status(context.workspace)):
            reporter.row(verb, "stop the watcher for '%s'" % context.workspace)
            actions += 1
        if maps_here():
            reporter.row(
                verb,
                "grepai workspace remove %s %s"
                % (context.workspace, context.proj_name),
            )
            actions += 1
        if agent_target in ("claude", "both") and _claude_grepai_ok(
            context.mcp_json, context.workspace
        ):
            reporter.row(verb, "claude mcp remove grepai -s project")
            actions += 1
        if agent_target in ("codex", "both") and stack.codex_mcp_get(
            "grepai-%s" % context.workspace
        ).returncode == 0:
            reporter.row(verb, "codex mcp remove grepai-%s" % context.workspace)
            actions += 1
        if os.path.isfile(os.path.join(context.root, ".code-intel")):
            reporter.row(verb, "rm .code-intel")
            actions += 1
        if os.path.isfile(context.refresh_script):
            if project.legacy_refresh_is_pristine(context.refresh_script):
                reporter.row(verb, "rm refresh-intel.sh")
                actions += 1
            else:
                reporter.row(
                    "note", "refresh-intel.sh is hand-modified — left alone"
                )
        if os.path.lexists(os.path.join(context.root, ".grepai")):
            reporter.row(verb, "rm -rf .grepai/")
            actions += 1
        if os.path.lexists(os.path.join(context.root, ".gitnexus")):
            reporter.row(verb, "rm -rf .gitnexus/")
            actions += 1
        for name in ("CLAUDE.md", "AGENTS.md"):
            if project.doc_state(os.path.join(context.root, name)) == "present":
                reporter.row(verb, "strip code-intel block from %s" % name)
                actions += 1
        for agent, path in agent_skills.managed_targets(context.root):
            reporter.row(
                verb,
                "rm %s routing skill at %s"
                % (agent, os.path.relpath(path, context.root)),
            )
            actions += 1
        if purge_collection:
            reporter.row(
                verb,
                "DELETE qdrant collection workspace_%s" % context.workspace,
            )
            actions += 1
        return actions

    if not apply:
        actions = removal_plan("would")
        reporter.say("")
        if actions == 0:
            reporter.say("Nothing to remove.")
            return 0
        reporter.say("Nothing was changed. To do the above:")
        reporter.say(
            "  agent-code-intel --remove --path %s --apply" % context.root
        )
        if not purge_collection:
            reporter.say(
                "  (add --purge-collection to also drop the qdrant collection)"
            )
        return 2

    if integrations.watcher_running(stack.watch_status(context.workspace)):
        stack.watch_stop(context.workspace)
        reporter.say("stopped watcher")
    if maps_here():
        stack.workspace_remove(context.workspace, context.proj_name)
        reporter.say("unmapped from '%s'" % context.workspace)
    if agent_target in ("claude", "both") and _claude_grepai_ok(
        context.mcp_json, context.workspace
    ):
        stack.claude_mcp_remove(context.root, "grepai", "project")
        reporter.say("claude: removed project 'grepai'")
    if agent_target in ("codex", "both") and stack.codex_mcp_get(
        "grepai-%s" % context.workspace
    ).returncode == 0:
        stack.codex_mcp_remove("grepai-%s" % context.workspace)
        reporter.say("codex: removed 'grepai-%s'" % context.workspace)

    code_intel_path = os.path.join(context.root, ".code-intel")
    if os.path.isfile(code_intel_path):
        _remove_path(code_intel_path)
    _remove_path(os.path.join(context.root, ".grepai"))
    _remove_path(os.path.join(context.root, ".gitnexus"))
    reporter.say("removed .code-intel, .grepai/ and .gitnexus/")

    if os.path.isfile(context.refresh_script):
        if project.legacy_refresh_is_pristine(context.refresh_script):
            _remove_path(context.refresh_script)
            reporter.say("removed refresh-intel.sh")
        else:
            reporter.say(
                "refresh-intel.sh is hand-modified — left it alone; remove it yourself"
            )

    for name in ("CLAUDE.md", "AGENTS.md"):
        path = os.path.join(context.root, name)
        result = project.remove_managed_doc(path)
        if result == "removed":
            reporter.say(
                "%s (the code-intel block was its only content)" % ("removed " + name)
            )
        elif result == "stripped":
            reporter.say("stripped the code-intel block from %s" % name)

    for agent, path in agent_skills.remove_managed_targets(context.root):
        reporter.say(
            "removed %s routing skill at %s"
            % (agent, os.path.relpath(path, context.root))
        )

    if purge_collection:
        http_url = "http://%s:%s" % (config.qdrant_host, config.qdrant_http_port)
        stack.qdrant_collection_delete(http_url, context.workspace)
        reporter.say("deleted qdrant collection workspace_%s" % context.workspace)

    project.registry_delete(registry_path, context.root)
    reporter.say("")
    reporter.say(
        "Done. The user-scope 'gitnexus' MCP entry was left in place — it serves"
    )
    reporter.say("every indexed repo, not just this one.")
    return 0


def _remove_path(path: str) -> None:
    """Remove a file, directory or symlink without following symlinks."""
    if not os.path.lexists(path):
        return
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    else:
        os.unlink(path)


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
            stdout,
            config,
            registry_path,
            _meta_config_file(loaded),
            version,
            agent_target,
            stack,
        )
        return 0
    return _status_text(
        reporter,
        context,
        status_all,
        registry_path,
        config,
        agent_target,
        stack,
    )


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


def _report_routing_status(
    reporter: Reporter, root: str, agent_target: str
) -> bool:
    """Render selected routing skills and return whether any has drift."""
    bad = False
    for agent, details in agent_skills.status(root, agent_target).items():
        skill_state = str(details["state"])
        relative = str(details["path"])
        if skill_state == "current":
            reporter.row("", "  %s routing skill current at %s" % (agent, relative))
            continue
        bad = True
        reporter.row(
            "",
            "  %s routing skill is %s at %s"
            % (agent, skill_state, relative),
        )
    return bad


# ---------------------------------------------------------------- text table --


def _status_text(
    reporter: Reporter,
    context: ProjectContext,
    status_all: bool,
    registry_path: str,
    config: Config,
    agent_target: str,
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
            drift |= _status_one(
                reporter, workspace, path, config, stack, agent_target
            )
    else:
        reporter.hr("code-intel status — %s" % context.root)
        drift = _status_one(
            reporter,
            context.workspace,
            context.root,
            config,
            stack,
            agent_target,
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
    agent_target: str | None = None,
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
        if agent_target is not None:
            _report_routing_status(reporter, root, agent_target)
        return True

    workspace, proj_name = _identity_names(root, identity, workspace)
    grepai_cfg = os.path.join(path, ".grepai", "config.yaml")
    refresh_script = os.path.join(path, "refresh-intel.sh")

    if not os.path.isdir(path):
        reporter.row(
            "GONE", "%s  %s  (directory no longer exists)" % (workspace, path)
        )
        if agent_target is not None:
            _report_routing_status(reporter, root, agent_target)
        return True

    routing_bad = (
        _report_routing_status(reporter, root, agent_target)
        if agent_target is not None
        else False
    )

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

    bad = routing_bad
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
    agent_target: str,
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
    projects = _json_projects(registry_path, config, agent_target, stack)
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
    registry_path: str,
    config: Config,
    agent_target: str,
    stack: integrations.Stack,
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
            entry["routing_skills"] = agent_skills.status(root, agent_target)
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
            entry["routing_skills"] = agent_skills.status(root, agent_target)
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

        routing_skills = agent_skills.status(root, agent_target)
        entry["routing_skills"] = routing_skills
        if not all(bool(details["ok"]) for details in routing_skills.values()):
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
    return _do_refresh(
        reporter,
        do_grepai,
        do_gitnexus,
        agent_target,
        context,
        config,
        stack,
    )


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
    agent_target: str,
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

    reporter.hr("Agent routing audit")
    drift |= _report_routing_status(reporter, context.root, agent_target)
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
