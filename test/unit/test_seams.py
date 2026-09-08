"""The narrow shared seams (issue #41 §3, §6, §7; issue #51 criterion 5):
CommandRunner, Reporter, and the Finding / ModeOutcome value types.
"""

import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_code_intel.commands import (
    CommandExit,
    CommandRunner,
    CommandSpec,
    Finding,
    ModeOutcome,
    Reporter,
)


class Runner(unittest.TestCase):
    def test_capture_returns_streams_and_code(self):
        result = CommandRunner().run(
            CommandSpec(argv=("sh", "-c", "printf out; printf err >&2; exit 3"))
        )
        self.assertEqual(result.returncode, 3)
        self.assertEqual(result.stdout, "out")
        self.assertEqual(result.stderr, "err")

    def test_spec_carries_cwd_and_env_explicitly(self):
        result = CommandRunner().run(
            CommandSpec(argv=("sh", "-c", "printf %s \"$MARK\""), env={"MARK": "seam"})
        )
        self.assertEqual(result.stdout, "seam")

    def test_spec_is_immutable(self):
        spec = CommandSpec(argv=("true",))
        with self.assertRaises(Exception):
            spec.cwd = "/x"  # type: ignore[misc]


class ReporterOrder(unittest.TestCase):
    def test_say_writes_immediately_and_in_order(self):
        out, err = io.StringIO(), io.StringIO()
        reporter = Reporter(out, err)
        reporter.say("first")
        out.write("<foreign>\n")
        reporter.say("third")
        self.assertEqual(out.getvalue(), "first\n<foreign>\nthird\n")

    def test_error_uses_die_wording_on_stderr(self):
        out, err = io.StringIO(), io.StringIO()
        Reporter(out, err).error("boom")
        self.assertEqual(err.getvalue(), "[ERROR: boom]\n")
        self.assertEqual(out.getvalue(), "")


class Values(unittest.TestCase):
    def test_finding_is_a_frozen_value(self):
        finding = Finding(result="drift", message="index is stale")
        with self.assertRaises(Exception):
            finding.result = "ok"  # type: ignore[misc]

    def test_mode_outcome_defaults_to_no_findings(self):
        self.assertEqual(ModeOutcome(exit_code=0).findings, ())

    def test_command_exit_carries_the_code(self):
        self.assertEqual(CommandExit(2).code, 2)


if __name__ == "__main__":
    unittest.main()
