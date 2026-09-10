"""Import purity — issue #48, decision 43 / issue #50 acceptance criterion 4.

Importing any of the seven modules must do no I/O, read no config, print
nothing and start no service. Each import runs in a fresh subprocess with the
CWD set to a scratch directory; the test fails if the module writes to that
directory, prints anything, or raises.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MODULES = (
    "agent_skills",
    "cli",
    "config",
    "project",
    "integrations",
    "commands",
    "hooks",
    "install",
)

_PROBE = (
    "import sys; sys.path.insert(0, %r)\n"
    "import agent_code_intel.%s\n"
)


class ImportPurity(unittest.TestCase):
    def _import_in_subprocess(self, module):
        with tempfile.TemporaryDirectory() as scratch:
            proc = subprocess.run(
                [sys.executable, "-c", _PROBE % (str(REPO), module)],
                capture_output=True, text=True, cwd=scratch, timeout=20,
                env={"PATH": "/usr/bin:/bin", "HOME": scratch},
            )
            leftovers = sorted(p.name for p in Path(scratch).iterdir())
        return proc, leftovers

    def test_each_module_imports_silently_and_touches_nothing(self):
        for module in MODULES:
            with self.subTest(module=module):
                proc, leftovers = self._import_in_subprocess(module)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(proc.stdout, "")
                self.assertEqual(proc.stderr, "")
                self.assertEqual(leftovers, [])

    def test_package_import_is_silent(self):
        with tempfile.TemporaryDirectory() as scratch:
            proc = subprocess.run(
                [sys.executable, "-c", "import sys; sys.path.insert(0, %r); import agent_code_intel" % str(REPO)],
                capture_output=True, text=True, cwd=scratch, timeout=20,
            )
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, "", ""))


if __name__ == "__main__":
    unittest.main()
