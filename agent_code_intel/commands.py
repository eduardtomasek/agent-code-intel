"""commands — mode orchestration, the subprocess seam, and the reporter.

Holds the imperative sequences for preview, apply, refresh, status (table and
JSON) and remove — none converted yet (issues #53–#56) — plus the narrow,
testable seams every mode shares (issue #41 §3, §6, §7; issue #51 criterion 5):

* :class:`CommandRunner` — the *one* generic seam for external processes. The
  :class:`CommandSpec` carries ``cwd``, ``env``, the stream mode and
  foreground/background explicitly; the caller owns the error policy.
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
import subprocess
from collections.abc import Mapping
from typing import TextIO


class CommandExit(Exception):
    """Carries the exit code of a subprocess whose output was already streamed
    to the user — :func:`agent_code_intel.cli.main` maps it straight to that
    code rather than to the generic error 1 (issue #48, decision 41)."""

    def __init__(self, code: int) -> None:
        super().__init__("subprocess exited %d" % code)
        self.code = code


@dataclasses.dataclass(frozen=True)
class CommandSpec:
    """A subprocess to run. ``stream`` is ``"capture"`` (collect stdout/stderr)
    or ``"inherit"`` (hand them straight to the user's terminal);
    ``background`` maps to the reference's explicit ``nohup … &`` delegations
    (issue #41 §8) — no general async, no timeouts, no PID management."""

    argv: tuple[str, ...]
    cwd: str | None = None
    env: Mapping[str, str] | None = None
    stream: str = "capture"
    background: bool = False


@dataclasses.dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class CommandRunner:
    """The single generic subprocess seam (issue #41 §3). A test double can
    record the argv, env, stream mode and ordering of one command without
    re-implementing the external stack."""

    def run(self, spec: CommandSpec) -> CommandResult:
        env = dict(spec.env) if spec.env is not None else None
        if spec.background:
            subprocess.Popen(
                list(spec.argv),
                cwd=spec.cwd,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return CommandResult(tuple(spec.argv), 0, "", "")
        if spec.stream == "inherit":
            completed = subprocess.run(list(spec.argv), cwd=spec.cwd, env=env)
            return CommandResult(tuple(spec.argv), completed.returncode, "", "")
        completed = subprocess.run(
            list(spec.argv),
            cwd=spec.cwd,
            env=env,
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

    def error(self, message: str) -> None:
        self._stderr.write("[ERROR: %s]\n" % message)


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


__all__ = [
    "CommandExit",
    "CommandSpec",
    "CommandResult",
    "CommandRunner",
    "Reporter",
    "Finding",
    "ModeOutcome",
]
