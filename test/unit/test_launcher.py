"""The checked-in source launcher must match the template — issue #50
acceptance criterion 1 ("source and installed launcher carry the same inline
gate").

The active ``agent-code-intel`` launcher is generated from
``agent_code_intel.install.render_launcher``; regenerating it here and diffing
keeps the two from drifting, and pins that the installed launcher (which #52
renders from the same function with an absolute shebang) shares the gate
byte-for-byte.
"""

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from agent_code_intel.install import RUNTIME_GATE, SOURCE_LAUNCHER, render_launcher


class Launcher(unittest.TestCase):
    def test_checked_in_source_launcher_is_up_to_date(self):
        on_disk = (REPO / "agent-code-intel").read_text()
        self.assertEqual(
            on_disk, SOURCE_LAUNCHER,
            "agent-code-intel is stale — regenerate it from "
            "agent_code_intel.install.SOURCE_LAUNCHER",
        )

    def test_source_launcher_starts_with_the_env_shebang(self):
        self.assertTrue(SOURCE_LAUNCHER.startswith("#!/usr/bin/env python3\n"))

    def test_gate_is_shared_verbatim_with_the_installed_launcher(self):
        installed = render_launcher(
            "#!/opt/py/bin/python3.11",
            package_parent="'/home/u/.local/lib/agent-code-intel'",
        )
        self.assertIn(RUNTIME_GATE.rstrip("\n"), SOURCE_LAUNCHER)
        self.assertIn(RUNTIME_GATE.rstrip("\n"), installed)

    def test_gate_parses_under_python_3_9_grammar(self):
        # The gate runs before the package import, so it must stay parseable by
        # old interpreters. compile() with no __future__ is a cheap proxy; the
        # real proof is test_runtime_gate.py running it under 3.9.6.
        compile(RUNTIME_GATE, "<gate>", "exec")
        for banned in ("match ", "tomllib", ":=", "f'", 'f"'):
            self.assertNotIn(banned, RUNTIME_GATE)


if __name__ == "__main__":
    unittest.main()
