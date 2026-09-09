"""integrations — adapters for the external stack.

One place per external tool — grepai, gitnexus, qdrant, ollama, the container
runtime, node — that knows how to call it and how to parse its human-readable
output into domain values (issue #48, decision 38). The parsing lives here, not
in the mode orchestration.

Every call goes through :class:`Stack`, which owns a single injectable
``execute`` seam (default: a real :mod:`subprocess` wrapper). A unit test hands
:class:`Stack` a fake ``execute`` and drives every probe with no real stack
installed. A missing binary is not an error here — it is the ``127`` the
reference's ``have`` guard / ``command not found`` already tolerated.

Qdrant counts as healthy only with both HTTP health and an open gRPC port
(decision 47); a GrepAI project name mapped elsewhere is ``CONFLICT``
(decision 48).

The status table and JSON status (issue #53) are the first consumers. Refresh
(issue #54) added the ``gitnexus analyze`` / ``gitnexus status`` /
``grepai watch --background`` adapters and the ``gitnexus_fresh`` /
``embeddings_not_persisted`` parsers. The ``.grepai/config.yaml``-writing
adapter lands with apply (issue #55).
"""

from __future__ import annotations

import dataclasses
import re
import shutil
import socket
import subprocess
from collections.abc import Mapping
from typing import Callable


@dataclasses.dataclass(frozen=True)
class Exec:
    """The result of running one external command."""

    returncode: int
    stdout: str
    stderr: str


def _real_exec(
    argv: tuple[str, ...], env: Mapping[str, str], cwd: str | None
) -> Exec:
    try:
        completed = subprocess.run(
            list(argv),
            cwd=cwd,
            env=dict(env),
            capture_output=True,
            text=True,
        )
    except OSError:
        # `command -v` said no, or it vanished between the check and the call:
        # the reference's `have x ||` / bare "command not found" both surface as
        # a non-zero status, never a crash.
        return Exec(127, "", "")
    return Exec(completed.returncode, completed.stdout, completed.stderr)


ExecFn = Callable[[tuple[str, ...], Mapping[str, str], "str | None"], Exec]

# Bounded wait on the qdrant health probes. Approved divergence (issue #35
# DEV-15): the reference's `curl` and `/dev/tcp` have no timeout, so
# `--status --json` hangs forever against a qdrant that accepts the TCP
# connection but never answers HTTP. `--status` must stay usable on a machine
# where the services are unhealthy, and a hung service is a kind of unhealthy —
# so the port caps the connect and the whole request. It still starts nothing.
_PROBE_CONNECT_TIMEOUT_S = 3
_PROBE_TOTAL_TIMEOUT_S = 5

_TRAILING_WS = re.compile(r"[ \t\r\n\f\v]+$")
_TRAILING_NONPRINT = re.compile(r"[^\x20-\x7e]+$")
_MODEL_WORD = re.compile(r"[Mm]odel")


class Stack:
    """Every external-tool call for one run, over one child environment.

    ``execute`` is the single seam (issue #41 §3): ``(argv, env, cwd) -> Exec``.
    """

    def __init__(
        self, env: Mapping[str, str], execute: ExecFn = _real_exec
    ) -> None:
        self._env = dict(env)
        self._path = self._env.get("PATH", "")
        self._exec = execute

    # -- generic ----------------------------------------------------------

    def have(self, name: str) -> bool:
        """``command -v <name>`` (``9406cce`` :137)."""
        return shutil.which(name, path=self._path) is not None

    def which(self, name: str) -> str:
        """``command -v <name>`` as a path, or ``""``."""
        return shutil.which(name, path=self._path) or ""

    def _run(self, argv: tuple[str, ...], cwd: str | None = None) -> Exec:
        return self._exec(tuple(argv), self._env, cwd)

    def _ok(self, *argv: str) -> bool:
        return self._run(argv).returncode == 0

    def first_line(self, *argv: str) -> str:
        """stdout of ``argv`` truncated to its first line (``… | head -1``)."""
        return self._run(argv).stdout.split("\n", 1)[0]

    # -- qdrant ---------------------------------------------------------------

    def qdrant_http_ok(self, http_url: str) -> bool:
        """``curl -s -w '%{http_code}' <url>/healthz`` == 200 (``9406cce``
        :581), with a bounded connect + total time (DEV-15)."""
        if not self.have("curl"):
            return False
        got = self._run(
            (
                "curl",
                "-s",
                "--connect-timeout",
                str(_PROBE_CONNECT_TIMEOUT_S),
                "--max-time",
                str(_PROBE_TOTAL_TIMEOUT_S),
                "-o",
                "/dev/null",
                "-w",
                "%{http_code}",
                http_url + "/healthz",
            )
        )
        return got.stdout.strip() == "200"

    def qdrant_grpc_ok(self, host: str, port: str) -> bool:
        """An open TCP connection to the gRPC port (``9406cce`` :585), with a
        bounded connect time (DEV-15). A refused port fails at once; a
        silently-dropping one now fails after the cap instead of the kernel's
        full SYN-retry window."""
        try:
            with socket.create_connection(
                (host, int(port)), timeout=_PROBE_CONNECT_TIMEOUT_S
            ):
                return True
        except (OSError, ValueError):
            return False

    # -- ollama -------------------------------------------------------------

    def ollama_up(self) -> bool:
        """``ollama list`` returns 0 (``9406cce`` :586)."""
        return self._ok("ollama", "list")

    def ollama_has_model(self, model: str) -> bool:
        """``ollama show <model>``, else a literal match in ``ollama list``
        (``9406cce`` :592)."""
        if self._ok("ollama", "show", model):
            return True
        return model in self._run(("ollama", "list")).stdout

    # -- grepai -----------------------------------------------------------

    def ws_show(self, workspace: str) -> str:
        """``grepai workspace show <ws>`` stdout, stderr and status discarded
        (``9406cce`` :597)."""
        return self._run(("grepai", "workspace", "show", workspace)).stdout

    def ws_exists(self, workspace: str) -> bool:
        """``grepai workspace show <ws>`` returns 0 (``9406cce`` :598)."""
        return self._ok("grepai", "workspace", "show", workspace)

    def watch_status(self, workspace: str) -> str:
        """``grepai watch --workspace <ws> --status 2>&1`` (``9406cce`` :735).

        The reference merges stderr into stdout; a captured pipe cannot
        reproduce the exact interleave, so both streams are concatenated —
        :func:`watcher_running` only does substring checks.
        """
        got = self._run(("grepai", "watch", "--workspace", workspace, "--status"))
        return got.stdout + got.stderr

    # -- container runtime ------------------------------------------------

    def container_cli(self) -> str:
        """First of docker / podman / nerdctl on PATH, else ``""``
        (``9406cce`` :873)."""
        for cli in ("docker", "podman", "nerdctl"):
            if self.have(cli):
                return cli
        return ""

    def container_daemon_ok(self, cli: str) -> bool:
        """``<cli> info`` returns 0 (``9406cce`` :884)."""
        return bool(cli) and self._ok(cli, "info")

    def container_inspect(
        self, cli: str, fmt: str, name: str, default: str
    ) -> str:
        """``<cli> inspect -f <fmt> <name>`` stdout, or ``default`` on failure
        (``9406cce`` :1825–:1830). Trailing newlines stripped, matching
        command substitution."""
        got = self._run((cli, "inspect", "-f", fmt, name))
        if got.returncode == 0:
            return got.stdout.rstrip("\n")
        return default

    # -- node -----------------------------------------------------------------

    def node_has_register_hooks(self) -> bool:
        """``module.registerHooks`` is a function on this node (``9406cce``
        :815)."""
        if not self.have("node"):
            return False
        return self._ok(
            "node",
            "-e",
            'process.exit(typeof require("node:module").registerHooks === '
            '"function" ? 0 : 1)',
        )

    # -- gitnexus -----------------------------------------------------------

    def gitnexus_runs(self) -> bool:
        """``gitnexus --version`` returns 0 (``9406cce`` :1801)."""
        return self._ok("gitnexus", "--version")

    def gitnexus_analyze_embeddings(self, cwd: str) -> Exec:
        """``gitnexus analyze --embeddings`` in ``cwd`` (``9406cce`` :2068).

        The reference streams this live; the port captures it and the mode
        replays it (approved divergence: same seam every other probe uses, and
        ``--refresh`` re-index output is L-tested only)."""
        return self._run(("gitnexus", "analyze", "--embeddings"), cwd=cwd)

    def gitnexus_analyze_force(self, cwd: str) -> Exec:
        """``gitnexus analyze --force`` in ``cwd`` (``9406cce`` :2075) — the
        structural-only retry the mode runs when the embeddings pass finished
        but persisted nothing."""
        return self._run(("gitnexus", "analyze", "--force"), cwd=cwd)

    def gitnexus_status(self, cwd: str) -> str:
        """``gitnexus status 2>&1`` in ``cwd`` (``9406cce`` :744), stderr merged
        into stdout; a 127 is the empty string. :func:`gitnexus_fresh` only does
        substring checks, so the exact interleave is not reproduced."""
        got = self._run(("gitnexus", "status"), cwd=cwd)
        return got.stdout + got.stderr

    # -- grepai watcher -----------------------------------------------------

    def watch_start_background(self, workspace: str) -> Exec:
        """``grepai watch --workspace <ws> --background`` (``9406cce`` :2054).

        ``--refresh`` does not redirect this — the reference lets it write
        straight to the user; the port captures it and the mode replays it."""
        return self._run(("grepai", "watch", "--workspace", workspace, "--background"))


# -- pure parsers (given a tool's captured output) -----------------------------


def mapped_path(ws_show_output: str, proj_name: str) -> str:
    """The path this project name maps to in a ``grepai workspace show``
    listing, or ``""`` (``9406cce`` :612).

    Matches ``- <name>: `` anywhere on the first such line, then strips trailing
    whitespace and any trailing non-printable decoration (grepai prints a ``✓``
    glyph in some subcommands).
    """

    needle = "- %s: " % proj_name
    for line in ws_show_output.splitlines():
        if needle in line:
            rest = line.split(needle, 1)[1]
            rest = _TRAILING_WS.sub("", rest)
            rest = _TRAILING_NONPRINT.sub("", rest)
            rest = _TRAILING_WS.sub("", rest)
            return rest
    return ""


def name_taken(ws_show_output: str, proj_name: str) -> bool:
    """This project name already maps somewhere in the workspace (``9406cce``
    :624)."""
    return bool(mapped_path(ws_show_output, proj_name))


def model_state(ws_show_output: str, embed_model: str) -> str:
    """``match`` / ``mismatch`` / ``unknown`` for the workspace's embedder
    (``9406cce`` :645)."""
    if embed_model in ws_show_output:
        return "match"
    if _MODEL_WORD.search(ws_show_output):
        return "mismatch"
    return "unknown"


def gitnexus_fresh(status_output: str) -> bool:
    """``gitnexus status`` reports the index up to date (``9406cce`` :745 —
    ``*"up-to-date"*|*"up to date"*``)."""
    return "up-to-date" in status_output or "up to date" in status_output


def embeddings_not_persisted(analyze_output: str) -> bool:
    """The one ``gitnexus analyze`` failure ``--refresh`` retries with
    ``--force`` (``9406cce`` :2073)."""
    return (
        "Embedding generation completed without persisted embeddings"
        in analyze_output
    )


def watcher_running(watch_status_output: str) -> bool:
    """Is the GrepAI watcher running, from ``grepai watch --status`` text
    (``9406cce`` :736). ``not running`` is checked before ``running``."""
    for stopped in ("not running", "stopped", "inactive"):
        if stopped in watch_status_output:
            return False
    for alive in ("running", "active"):
        if alive in watch_status_output:
            return True
    return False
