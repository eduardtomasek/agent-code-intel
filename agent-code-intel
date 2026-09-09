#!/usr/bin/env python3
"""agent-code-intel — thin launcher: gate the interpreter, then hand off.

Generated from ``agent_code_intel.install.render_launcher``. Do not edit by
hand; edit the template and regenerate (``test/unit/test_launcher.py`` checks
this file still matches).
"""

import sys as _sys

if _sys.version_info < (3, 11):
    _v = _sys.version_info
    _sys.stderr.write(
        "[ERROR: agent-code-intel requires Python 3.11 or newer "
        "(found %d.%d.%d)]\n" % (_v[0], _v[1], _v[2])
    )
    raise SystemExit(1)

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

from agent_code_intel.cli import main

raise SystemExit(
    main(sys.argv[1:], os.environ, os.getcwd(), sys.stdout, sys.stderr)
)
