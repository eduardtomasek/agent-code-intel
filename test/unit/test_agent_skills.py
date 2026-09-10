"""Managed routing-skill lifecycle."""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_code_intel import agent_skills
from agent_code_intel.config import CliError


class AgentSkills(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="aci-skills-")

    def test_agent_target_selects_only_its_own_path(self):
        agent_skills.install_targets(self.root, "claude", False)
        self.assertTrue(os.path.isfile(agent_skills.target_paths(self.root, "claude")[0][1]))
        self.assertFalse(os.path.exists(agent_skills.target_paths(self.root, "codex")[0][1]))

        other = tempfile.mkdtemp(prefix="aci-skills-")
        agent_skills.install_targets(other, "codex", False)
        self.assertFalse(os.path.exists(agent_skills.target_paths(other, "claude")[0][1]))
        self.assertTrue(os.path.isfile(agent_skills.target_paths(other, "codex")[0][1]))

    def test_both_copies_are_byte_identical(self):
        agent_skills.install_targets(self.root, "both", False)
        for skill in agent_skills.SKILLS:
            paths = [
                path for _, path in agent_skills.target_paths(self.root, "both", skill)
            ]
            self.assertEqual(Path(paths[0]).read_bytes(), Path(paths[1]).read_bytes())
            self.assertEqual(Path(paths[0]).read_text(), agent_skills.source_text(skill))

    def test_routing_skill_includes_code_context_rules(self):
        source = agent_skills.source_text()
        self.assertIn("## Code-context rules", source)
        self.assertIn("cross-module calls belong to `rg`/`ast-grep`", source)
        self.assertIn("not the knowledge graphs", source)
        self.assertIn("Derive the exact definition range", source)
        self.assertIn("never guess it or truncate it", source)

    def test_status_only_reports_selected_agents(self):
        agent_skills.install_targets(self.root, "claude", False)
        self.assertEqual(set(agent_skills.status(self.root, "claude")), {"claude"})
        self.assertEqual(
            set(agent_skills.status(self.root, "claude")["claude"]),
            set(agent_skills.SKILLS),
        )
        both = agent_skills.status(self.root, "both")
        self.assertTrue(both["claude"][agent_skills.SKILL_NAME]["ok"])
        self.assertEqual(both["codex"][agent_skills.SKILL_NAME]["state"], "missing")
        self.assertEqual(both["codex"]["code-context"]["state"], "missing")
        self.assertFalse(both["codex"][agent_skills.SKILL_NAME]["ok"])

    def test_all_managed_skills_follow_the_full_lifecycle(self):
        expected = {
            (skill, agent)
            for skill in agent_skills.SKILLS
            for agent in ("claude", "codex")
        }
        installed = agent_skills.install_targets(self.root, "both", False)
        self.assertEqual({(skill, agent) for skill, agent, _ in installed}, expected)
        self.assertEqual(
            {
                (skill, agent)
                for skill in agent_skills.SKILLS
                for agent, _ in agent_skills.target_paths(self.root, "both", skill)
            },
            expected,
        )

        statuses = agent_skills.status(self.root, "both")
        self.assertEqual(set(statuses), {"claude", "codex"})
        self.assertEqual(set(statuses["claude"]), set(agent_skills.SKILLS))
        self.assertTrue(
            all(details["ok"] for skills in statuses.values() for details in skills.values())
        )

        managed = agent_skills.managed_targets(self.root)
        self.assertEqual({(skill, agent) for skill, agent, _ in managed}, expected)
        removed = agent_skills.remove_managed_targets(self.root)
        self.assertEqual({(skill, agent) for skill, agent, _ in removed}, expected)

    def test_current_skill_is_a_true_noop(self):
        agent_skills.install_targets(self.root, "claude", False)
        path = agent_skills.target_paths(self.root, "claude")[0][1]
        before = os.stat(path).st_mtime_ns
        time.sleep(0.002)
        self.assertEqual(
            agent_skills.install_targets(self.root, "claude", False),
            (
                (agent_skills.SKILL_NAME, "claude", "current"),
                ("code-context", "claude", "current"),
            ),
        )
        self.assertEqual(os.stat(path).st_mtime_ns, before)

    def test_managed_drift_is_repaired(self):
        agent_skills.install_targets(self.root, "claude", False)
        path = agent_skills.target_paths(self.root, "claude")[0][1]
        Path(path).write_text(agent_skills.MANAGED_MARKER + "\nold\n")
        self.assertEqual(
            agent_skills.install_targets(self.root, "claude", False),
            (
                (agent_skills.SKILL_NAME, "claude", "updated"),
                ("code-context", "claude", "current"),
            ),
        )
        self.assertEqual(Path(path).read_text(), agent_skills.source_text())

    def test_foreign_skill_requires_force(self):
        path = agent_skills.target_paths(self.root, "codex")[0][1]
        os.makedirs(os.path.dirname(path))
        Path(path).write_text("user skill\n")
        with self.assertRaises(CliError):
            agent_skills.validate_targets(self.root, "codex", False)
        self.assertEqual(Path(path).read_text(), "user skill\n")
        agent_skills.install_targets(self.root, "codex", True)
        self.assertEqual(Path(path).read_text(), agent_skills.source_text())

    def test_symlinked_parent_is_rejected(self):
        outside = tempfile.mkdtemp(prefix="aci-skills-outside-")
        os.symlink(outside, os.path.join(self.root, ".agents"))
        with self.assertRaises(CliError):
            agent_skills.validate_targets(self.root, "codex", True)
        self.assertEqual(os.listdir(outside), [])

    def test_remove_deletes_both_managed_skills_and_preserves_foreign(self):
        agent_skills.install_targets(self.root, "both", False)
        claude = agent_skills.target_paths(self.root, "claude")[0][1]
        Path(claude).write_text("foreign\n")
        removed = agent_skills.remove_managed_targets(self.root)
        self.assertEqual(
            {(skill, agent) for skill, agent, _ in removed},
            {
                (agent_skills.SKILL_NAME, "codex"),
                ("code-context", "claude"),
                ("code-context", "codex"),
            },
        )
        self.assertEqual(Path(claude).read_text(), "foreign\n")
        self.assertFalse(os.path.exists(agent_skills.target_paths(self.root, "codex")[0][1]))
        self.assertFalse(
            os.path.exists(
                agent_skills.target_paths(self.root, "both", "code-context")[0][1]
            )
        )


if __name__ == "__main__":
    unittest.main()
