"""Runtime gate unit test — ledger row RT-11, divergence DEV-1 / text TXT-2.

The source launcher, run by an interpreter below 3.11, must print exactly the
approved one-line diagnostic to stderr and exit 1 with no traceback, before it
imports anything from the ``agent_code_intel`` package (issue #48, decision 3).

This test is the fast, direct check and the one that runs even when no
sub-3.11 interpreter is on PATH (it skips).
"""

import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LAUNCHER = REPO / "agent-code-intel"

_MESSAGE = "[ERROR: agent-code-intel requires Python 3.11 or newer (found {}.{}.{})]\n"


def _old_python():
    """An interpreter strictly below 3.11, or None."""
    for cand in ("/usr/bin/python3", "python3.9", "python3.10"):
        try:
            out = subprocess.run(
                [cand, "-c", "import sys;print('%d %d %d' % sys.version_info[:3])"],
                capture_output=True, text=True, timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if out.returncode != 0:
            continue
        major, minor, micro = (int(x) for x in out.stdout.split())
        if (major, minor) < (3, 11):
            return cand, (major, minor, micro)
    return None


class RuntimeGate(unittest.TestCase):
    def test_rejects_sub_3_11_with_the_approved_message_and_no_traceback(self):
        found = _old_python()
        if found is None:
            self.skipTest("no Python < 3.11 available to exercise the gate")
        interp, ver = found
        proc = subprocess.run(
            [interp, str(LAUNCHER), "--version"],
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, "")
        self.assertEqual(proc.stderr, _MESSAGE.format(*ver))
        self.assertNotIn("Traceback", proc.stderr)

    def test_the_running_interpreter_passes_the_gate(self):
        # Whatever runs this suite is >= 3.11 (the contract version), so the
        # gate must be transparent: --version succeeds.
        self.assertGreaterEqual(sys.version_info[:2], (3, 11))
        proc = subprocess.run(
            [sys.executable, str(LAUNCHER), "--version"],
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual((proc.returncode, proc.stdout), (0, "agent-code-intel 6.0.0\n"))


if __name__ == "__main__":
    unittest.main()
