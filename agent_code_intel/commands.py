"""commands — mode orchestration and the one subprocess seam.

Holds the imperative sequences for preview, apply, refresh, status (table and
JSON) and remove, plus ``CommandRunner`` — the single generic seam for
external processes (issue #48, decisions 37, 45). Preview and apply keep their
own step order and the existing non-atomic side-effect ordering; they share
probes and pure sub-decisions, not a universal action plan.

``CommandExit`` (raised to preserve the exit code of an already-streamed
subprocess) is one of the three error paths (decision 41).

Not converted yet: status lands in issue #53, refresh in #54, preview/apply in
#55, remove in #56.
"""

from __future__ import annotations


class CommandExit(Exception):
    """Carries the exit code of a subprocess whose output was already streamed
    to the user — :func:`agent_code_intel.cli.main` maps it straight to that
    code rather than to the generic error 1 (issue #48, decision 41)."""

    def __init__(self, code: int) -> None:
        super().__init__("subprocess exited %d" % code)
        self.code = code
