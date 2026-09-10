"""Repo-local Claude and Codex SessionStart hook lifecycle (issues #82/#83)."""

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

    def test_codex_install_writes_exact_portable_registration(self):
        expected = (
            '{\n'
            '  "hooks": {\n'
            '    "SessionStart": [\n'
            '      {\n'
            '        "hooks": [\n'
            '          {\n'
            '            "type": "command",\n'
            '            "command": "/usr/bin/env python3 \\\"$(git rev-parse --show-toplevel)/.claude/helpers/code-context-hint.py\\\"",\n'
            '            "timeout": 5\n'
            '          }\n'
            '        ]\n'
            '      }\n'
            '    ]\n'
            '  }\n'
            '}\n'
        )

        result = hooks.install(self.root, "codex")

        self.assertTrue(result.changed)
        self.assertTrue(result.registration_changed)
        self.assertEqual(
            Path(self.root, hooks.CODEX_SETTINGS_RELATIVE).read_text(), expected
        )
        self.assertEqual(
            Path(self.root, hooks.SCRIPT_RELATIVE).read_text(), hooks.source_text()
        )

    def test_codex_install_is_idempotent(self):
        hooks.install(self.root, "codex")
        script = Path(self.root, hooks.SCRIPT_RELATIVE)
        settings = Path(self.root, hooks.CODEX_SETTINGS_RELATIVE)
        before = (script.stat().st_mtime_ns, settings.stat().st_mtime_ns)

        result = hooks.install(self.root, "codex")

        self.assertFalse(result.changed)
        self.assertFalse(result.registration_changed)
        self.assertEqual(
            (script.stat().st_mtime_ns, settings.stat().st_mtime_ns), before
        )

    def test_codex_install_merges_foreign_settings(self):
        settings_path = Path(self.root, hooks.CODEX_SETTINGS_RELATIVE)
        settings_path.parent.mkdir(parents=True)
        foreign = {
            "hooks": {
                "SessionStart": [
                    {"hooks": [{"type": "command", "command": "foreign"}]}
                ],
                "Stop": [{"hooks": [{"type": "command", "command": "stop"}]}],
            },
            "notify": {"enabled": True},
        }
        settings_path.write_text(json.dumps(foreign, indent=2) + "\n")

        hooks.install(self.root, "codex")

        settings = json.loads(settings_path.read_text())
        self.assertEqual(settings["notify"], foreign["notify"])
        self.assertEqual(settings["hooks"]["Stop"], foreign["hooks"]["Stop"])
        self.assertEqual(
            settings["hooks"]["SessionStart"][0],
            foreign["hooks"]["SessionStart"][0],
        )
        self.assertEqual(
            settings["hooks"]["SessionStart"][-1], hooks.CODEX_HOOK_GROUP
        )

    def test_codex_remove_preserves_shared_script_used_by_claude(self):
        hooks.install(self.root, "both")

        result = hooks.remove(self.root, "codex")

        self.assertIn(hooks.CODEX_SETTINGS_RELATIVE, result.removed)
        self.assertTrue(Path(self.root, hooks.SCRIPT_RELATIVE).exists())
        self.assertTrue(Path(self.root, hooks.SETTINGS_RELATIVE).exists())
        self.assertFalse(Path(self.root, hooks.CODEX_SETTINGS_RELATIVE).exists())

        hooks.remove(self.root, "claude")
        self.assertFalse(Path(self.root, hooks.SCRIPT_RELATIVE).exists())

    def test_both_status_reports_each_registration(self):
        hooks.install(self.root, "both")

        status = hooks.status(self.root, "both")

        self.assertTrue(status["ok"])
        self.assertEqual(set(status["agents"]), {"claude", "codex"})
        self.assertEqual(
            status["agents"]["codex"]["settings_path"], hooks.CODEX_SETTINGS_RELATIVE
        )

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
