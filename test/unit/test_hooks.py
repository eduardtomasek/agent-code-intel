"""Repo-local Claude SessionStart hook lifecycle (issue #82)."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_code_intel import hooks


class HookLifecycle(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="aci-hook-")

    def test_install_writes_asset_and_merges_foreign_settings(self):
        settings_path = Path(self.root, ".claude", "settings.json")
        settings_path.parent.mkdir(parents=True)
        foreign = {
            "permissions": {"allow": ["Bash(ls)"]},
            "hooks": {
                "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "foreign"}]}],
                "SessionStart": [{"hooks": [{"type": "command", "command": "foreign-start"}]}],
            },
        }
        settings_path.write_text(json.dumps(foreign, indent=2) + "\n")

        hooks.install(self.root)

        script = Path(self.root, hooks.SCRIPT_RELATIVE)
        self.assertEqual(script.read_text(), hooks.source_text())
        settings = json.loads(settings_path.read_text())
        self.assertEqual(settings["permissions"], foreign["permissions"])
        self.assertEqual(settings["hooks"]["UserPromptSubmit"], foreign["hooks"]["UserPromptSubmit"])
        session = settings["hooks"]["SessionStart"]
        self.assertEqual(session[0], foreign["hooks"]["SessionStart"][0])
        self.assertEqual(session[-1], hooks.CLAUDE_HOOK_GROUP)
        self.assertNotIn("statusLine", settings)

    def test_install_is_idempotent(self):
        hooks.install(self.root)
        script = Path(self.root, hooks.SCRIPT_RELATIVE)
        settings = Path(self.root, hooks.SETTINGS_RELATIVE)
        before = (script.stat().st_mtime_ns, settings.stat().st_mtime_ns)

        hooks.install(self.root)

        self.assertEqual(
            (script.stat().st_mtime_ns, settings.stat().st_mtime_ns), before
        )

    def test_unreadable_settings_are_left_untouched_and_script_is_written(self):
        settings_path = Path(self.root, hooks.SETTINGS_RELATIVE)
        settings_path.parent.mkdir(parents=True)
        settings_path.write_text("not valid json{")

        result = hooks.install(self.root)

        self.assertEqual(settings_path.read_text(), "not valid json{")
        self.assertTrue(Path(self.root, hooks.SCRIPT_RELATIVE).is_file())
        self.assertIn("unreadable", result.warning)

    def test_status_reports_drift_and_remove_preserves_foreign_content(self):
        hooks.install(self.root)
        script = Path(self.root, hooks.SCRIPT_RELATIVE)
        script.write_text("user edit\n")
        settings_path = Path(self.root, hooks.SETTINGS_RELATIVE)
        settings = json.loads(settings_path.read_text())
        settings["permissions"] = {"allow": ["Bash(ls)"]}
        settings["hooks"]["SessionStart"].insert(
            0, {"hooks": [{"type": "command", "command": "foreign-start"}]}
        )
        settings_path.write_text(json.dumps(settings, indent=2) + "\n")

        status = hooks.status(self.root)
        self.assertEqual(status["state"], "managed-drift")
        self.assertFalse(status["ok"])

        hooks.remove(self.root)

        self.assertFalse(script.exists())
        remaining = json.loads(settings_path.read_text())
        self.assertEqual(remaining["permissions"], {"allow": ["Bash(ls)"]})
        self.assertEqual(
            remaining["hooks"]["SessionStart"],
            [{"hooks": [{"type": "command", "command": "foreign-start"}]}],
        )

    def test_remove_deletes_empty_settings_file(self):
        hooks.install(self.root)
        hooks.remove(self.root)

        self.assertFalse(Path(self.root, ".claude").exists())


if __name__ == "__main__":
    unittest.main()
