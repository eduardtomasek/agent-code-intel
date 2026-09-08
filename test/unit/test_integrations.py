"""External-stack adapters (issue #53): the pure output parsers, and the
:class:`Stack` probes driven through a fake ``execute`` seam with no real
grepai / gitnexus / ollama / docker / node installed.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_code_intel import integrations
from agent_code_intel.integrations import Exec, Stack


class MappedPath(unittest.TestCase):
    def test_two_space_form(self):
        out = "Workspace: w\nProjects (1):\n  - widget: /home/me/widget\n"
        self.assertEqual(integrations.mapped_path(out, "widget"), "/home/me/widget")

    def test_four_space_and_trailing_glyph_stripped(self):
        out = "    - widget: /home/me/widget ✓\n"
        self.assertEqual(integrations.mapped_path(out, "widget"), "/home/me/widget")

    def test_literal_name_not_a_regex(self):
        out = "  - api.v2: /srv/api\n  - api-v2: /srv/other\n"
        self.assertEqual(integrations.mapped_path(out, "api.v2"), "/srv/api")

    def test_needle_colon_space_prevents_prefix_match(self):
        out = "  - my-test-intel: /a\n  - test-intel: /b\n"
        self.assertEqual(integrations.mapped_path(out, "test-intel"), "/b")

    def test_absent_is_empty_string(self):
        self.assertEqual(integrations.mapped_path("Projects (0):\n", "widget"), "")

    def test_first_match_wins(self):
        out = "  - w: /first\n  - w: /second\n"
        self.assertEqual(integrations.mapped_path(out, "w"), "/first")


class NameTaken(unittest.TestCase):
    def test_true_when_mapped_somewhere(self):
        self.assertTrue(integrations.name_taken("  - w: /x\n", "w"))

    def test_false_when_absent(self):
        self.assertFalse(integrations.name_taken("nothing here\n", "w"))


class ModelState(unittest.TestCase):
    def test_match_when_model_named(self):
        self.assertEqual(
            integrations.model_state("embedder: nomic-embed-text\n", "nomic-embed-text"),
            "match",
        )

    def test_mismatch_when_some_other_model_line(self):
        self.assertEqual(
            integrations.model_state("Model: some-other\n", "nomic-embed-text"),
            "mismatch",
        )

    def test_unknown_when_no_model_information(self):
        self.assertEqual(
            integrations.model_state("Workspace: w\n", "nomic-embed-text"), "unknown"
        )


class WatcherRunning(unittest.TestCase):
    def test_not_running_beats_running_substring(self):
        self.assertFalse(integrations.watcher_running("watcher is not running"))

    def test_stopped_and_inactive(self):
        self.assertFalse(integrations.watcher_running("status: stopped"))
        self.assertFalse(integrations.watcher_running("state inactive"))

    def test_running_and_active(self):
        self.assertTrue(integrations.watcher_running("watcher running (pid 42)"))
        self.assertTrue(integrations.watcher_running("active"))

    def test_unrecognised_is_not_running(self):
        self.assertFalse(integrations.watcher_running(""))
        self.assertFalse(integrations.watcher_running("grepai: command not found"))


def _fake(table):
    """table: {argv-tuple: Exec}. Anything not listed → 127/empty (absent)."""

    def execute(argv, env, cwd):
        return table.get(tuple(argv), Exec(127, "", ""))

    return execute


class StackProbes(unittest.TestCase):
    def _stack(self, table, path=""):
        return Stack({"PATH": path}, execute=_fake(table))

    def test_qdrant_http_needs_curl_on_path(self):
        # curl not on the (empty) PATH → False without even trying
        stack = self._stack({})
        self.assertFalse(stack.qdrant_http_ok("http://127.0.0.1:6333"))

    def test_qdrant_grpc_refused_port_is_false(self):
        stack = self._stack({})
        # 9 is discard; nothing listens → connection refused → False, fast
        self.assertFalse(stack.qdrant_grpc_ok("127.0.0.1", "9"))

    def test_qdrant_grpc_non_numeric_port_is_false(self):
        self.assertFalse(self._stack({}).qdrant_grpc_ok("127.0.0.1", "nope"))

    def test_ollama_has_model_falls_back_to_list_grep(self):
        table = {
            ("ollama", "show", "m"): Exec(1, "", "not found"),
            ("ollama", "list"): Exec(0, "NAME\nm:latest  123\n", ""),
        }
        self.assertTrue(self._stack(table).ollama_has_model("m"))

    def test_ollama_has_model_false_when_absent_everywhere(self):
        table = {
            ("ollama", "show", "m"): Exec(1, "", ""),
            ("ollama", "list"): Exec(0, "NAME\nother\n", ""),
        }
        self.assertFalse(self._stack(table).ollama_has_model("m"))

    def test_ws_show_swallows_failure(self):
        self.assertEqual(self._stack({}).ws_show("w"), "")

    def test_ws_exists_is_return_code(self):
        table = {("grepai", "workspace", "show", "w"): Exec(0, "Workspace: w\n", "")}
        self.assertTrue(self._stack(table).ws_exists("w"))
        self.assertFalse(self._stack({}).ws_exists("w"))

    def test_watch_status_merges_streams(self):
        table = {
            ("grepai", "watch", "--workspace", "w", "--status"): Exec(
                0, "out-part ", "err-part"
            )
        }
        self.assertEqual(self._stack(table).watch_status("w"), "out-part err-part")

    def test_container_cli_empty_without_any_runtime(self):
        self.assertEqual(self._stack({}).container_cli(), "")

    def test_container_inspect_default_on_failure(self):
        self.assertEqual(
            self._stack({}).container_inspect("docker", "{{.X}}", "c", "absent"),
            "absent",
        )

    def test_container_inspect_strips_trailing_newlines(self):
        table = {("docker", "inspect", "-f", "{{.X}}", "c"): Exec(0, "running\n", "")}
        self.assertEqual(
            self._stack(table).container_inspect("docker", "{{.X}}", "c", "absent"),
            "running",
        )

    def test_first_line_truncates(self):
        table = {("grepai", "version"): Exec(0, "grepai 1.2.3\n(build info)\n", "")}
        self.assertEqual(self._stack(table).first_line("grepai", "version"), "grepai 1.2.3")

    def test_node_register_hooks_false_without_node(self):
        self.assertFalse(self._stack({}).node_has_register_hooks())


if __name__ == "__main__":
    unittest.main()
