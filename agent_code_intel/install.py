"""install — self-install, upgrade from v2/v3, and the launcher templates.

Only the launcher templates are needed this slice (issue #50): both the
source launcher checked in at the repo root and the launcher that
``--install`` will later write must carry the *same* inline Python-3.11 gate
(issue #50, acceptance criterion 1). Keeping the gate here as one string and
rendering both launchers from it is how "identical" is guaranteed rather than
hoped for.

The install / upgrade machinery itself (issue #48, decisions 56–67) lands in
issue #52.
"""

from __future__ import annotations

# The inline runtime gate. It runs *before* the ``agent_code_intel`` package is
# imported, so it must parse and execute under Python 3.9 (the oldest
# interpreter a stock macOS is likely to reach for) — no f-strings with ``=``,
# no ``match``, no ``tomllib``, nothing 3.10+. On an interpreter below 3.11 it
# prints the approved one-line diagnostic (issue #48, decision 3; issue #35,
# TXT-2) and exits 1 with no traceback.
RUNTIME_GATE = '''\
import sys as _sys

if _sys.version_info < (3, 11):
    _v = _sys.version_info
    _sys.stderr.write(
        "[ERROR: agent-code-intel requires Python 3.11 or newer "
        "(found %d.%d.%d)]\\n" % (_v[0], _v[1], _v[2])
    )
    raise SystemExit(1)
'''

_LAUNCHER_BODY = '''\
"""agent-code-intel — thin launcher: gate the interpreter, then hand off.

Generated from ``agent_code_intel.install.render_launcher``. Do not edit by
hand; edit the template and regenerate (``test/unit/test_launcher.py`` checks
this file still matches).
"""

{gate}

import os
import sys

sys.path.insert(0, {package_parent})

from agent_code_intel.cli import main

raise SystemExit(
    main(sys.argv[1:], os.environ, os.getcwd(), sys.stdout, sys.stderr)
)
'''

# How each launcher locates the importable ``agent_code_intel`` package
# (issue #48, decision 2 / issue #39):
#   source     — the package sits next to this file in the checkout
#   installed  — an absolute lib directory the installer bakes in
_SOURCE_PACKAGE_PARENT = "os.path.dirname(os.path.realpath(__file__))"


def render_launcher(shebang: str, package_parent: str = _SOURCE_PACKAGE_PARENT) -> str:
    """Return the full text of a launcher.

    ``shebang`` is the first line (``#!/usr/bin/env python3`` for the source
    launcher; an absolute ``#!<sys.executable>`` for the installed one, issue
    #48 decision 2). ``package_parent`` is a Python expression that evaluates
    to the directory containing the ``agent_code_intel`` package.
    """

    return shebang.rstrip("\n") + "\n" + _LAUNCHER_BODY.format(
        gate=RUNTIME_GATE.rstrip("\n"),
        package_parent=package_parent,
    )


SOURCE_LAUNCHER = render_launcher("#!/usr/bin/env python3")
