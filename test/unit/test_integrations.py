"""External-stack adapters (issue #53): the pure output parsers, and the
:class:`Stack` probes driven through a fake ``execute`` seam with no real
grepai / gitnexus / ollama / docker / node installed.
"""

import os
import sys
import tempfile
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


class GitnexusFresh(unittest.TestCase):
    def test_both_spellings_are_fresh(self):
        self.assertTrue(integrations.gitnexus_fresh("Index: up-to-date"))
        self.assertTrue(integrations.gitnexus_fresh("the index is up to date"))

    def test_anything_else_is_stale(self):
        self.assertFalse(integrations.gitnexus_fresh("Index: 3 files changed"))
        self.assertFalse(integrations.gitnexus_fresh(""))


class EmbeddingsNotPersisted(unittest.TestCase):
    def test_the_one_retryable_message(self):
        self.assertTrue(
            integrations.embeddings_not_persisted(
                "...\nEmbedding generation completed without persisted embeddings\n"
            )
        )

    def test_other_failures_are_not_retryable(self):
        self.assertFalse(integrations.embeddings_not_persisted("segfault"))


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

    def test_qdrant_probes_are_time_bounded(self):  # DEV-15
        seen = {}

        def execute(argv, env, cwd):
            seen["argv"] = argv
            return Exec(0, "200", "")

        stack = Stack({"PATH": "/usr/bin:/bin"}, execute=execute)
        self.assertTrue(stack.qdrant_http_ok("http://127.0.0.1:6333"))
        self.assertIn("--connect-timeout", seen["argv"])
        self.assertIn("--max-time", seen["argv"])
        # gRPC: a refused local port still returns fast and False
        self.assertFalse(stack.qdrant_grpc_ok("127.0.0.1", "9"))

    def test_qdrant_grpc_refused_port_is_false(self):
        stack = self._stack({})
        # 9 is discard; nothing listens → connection refused → False, fast
        self.assertFalse(stack.qdrant_grpc_ok("127.0.0.1", "9"))

    def test_qdrant_grpc_non_numeric_port_is_false(self):
        self.assertFalse(self._stack({}).qdrant_grpc_ok("127.0.0.1", "nope"))

    def _ctags_on_path(self):
        """A real file named ctags on a real PATH, so ``have`` finds it without
        depending on what this machine has installed."""
        d = tempfile.mkdtemp(prefix="aci-ctags-")
        stub = os.path.join(d, "ctags")
        with open(stub, "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\nexit 1\n")
        os.chmod(stub, 0o755)
        return d

    def test_ctags_absent_is_not_universal(self):  # issue #99
        stack = self._stack({})
        self.assertFalse(stack.ctags_is_universal())

    def test_bsd_ctags_on_path_is_not_universal(self):  # issue #99
        # What a Mac without Homebrew has: /usr/bin/ctags exists, rejects
        # --version with usage on stderr, and leaves stdout empty.
        table = {("ctags", "--version"): Exec(1, "", "ctags: illegal option -- -")}
        stack = self._stack(table, path=self._ctags_on_path())
        self.assertTrue(stack.have("ctags"))
        self.assertFalse(stack.ctags_is_universal())

    def test_universal_ctags_on_path_is_universal(self):  # issue #99
        banner = "Universal Ctags 6.2.1, Copyright (C) 2015-2025 Universal Ctags Team\n"
        table = {("ctags", "--version"): Exec(0, banner, "")}
        stack = self._stack(table, path=self._ctags_on_path())
        self.assertTrue(stack.ctags_is_universal())

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

    def test_node_version_ok_false_without_node(self):
        self.assertFalse(self._stack({}).node_version_ok())

    def test_watch_start_background_argv(self):  # issue #54
        seen = {}

        def execute(argv, env, cwd):
            seen["argv"], seen["cwd"] = tuple(argv), cwd
            return Exec(0, "started", "")

        stack = Stack({"PATH": ""}, execute=execute)
        result = stack.watch_start_background("myws")
        self.assertEqual(
            seen["argv"], ("grepai", "watch", "--workspace", "myws", "--background")
        )
        self.assertEqual(result.stdout, "started")

    def test_gitnexus_analyze_runs_in_cwd(self):  # issue #54 AC 4
        seen = {}

        def execute(argv, env, cwd):
            seen.setdefault("calls", []).append((tuple(argv), cwd))
            return Exec(0, "", "")

        stack = Stack({"PATH": ""}, execute=execute)
        stack.gitnexus_analyze_embeddings("/proj/root")
        stack.gitnexus_analyze_force("/proj/root")
        self.assertEqual(
            seen["calls"],
            [
                (("gitnexus", "analyze", "--embeddings"), "/proj/root"),
                (("gitnexus", "analyze", "--force"), "/proj/root"),
            ],
        )

    def test_gitnexus_status_merges_streams_and_runs_in_cwd(self):
        table = {("gitnexus", "status"): Exec(0, "out ", "err")}
        stack = self._stack(table)
        self.assertEqual(stack.gitnexus_status("/r"), "out err")
        self.assertEqual(self._stack({}).gitnexus_status("/r"), "")

    def test_claude_mcp_get_uses_supported_cli_arguments(self):
        seen = {}

        def execute(argv, env, cwd):
            seen["argv"] = tuple(argv)
            return Exec(0, "gitnexus: connected", "")

        stack = Stack({"PATH": ""}, execute=execute)
        result = stack.claude_mcp_get("gitnexus", "user")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(seen["argv"], ("claude", "mcp", "get", "gitnexus"))

    def test_remove_adapters_use_reference_argv_and_cwd(self):
        calls = []

        def execute(argv, env, cwd):
            calls.append((tuple(argv), cwd))
            return Exec(0, "", "")

        stack = Stack({"PATH": ""}, execute=execute)
        stack.claude_mcp_remove("/project", "grepai", "project")
        stack.codex_mcp_remove("grepai-team")
        stack.qdrant_collection_delete("http://127.0.0.1:6333", "team")
        self.assertEqual(
            calls,
            [
                (("claude", "mcp", "remove", "grepai", "-s", "project"), "/project"),
                (("codex", "mcp", "remove", "grepai-team"), None),
                (("curl", "-s", "-X", "DELETE", "http://127.0.0.1:6333/collections/workspace_team"), None),
            ],
        )


class NodeVersionGate(unittest.TestCase):
    """The Node minimum follows gitnexus's published `engines`, so the gate is
    a version comparison and not a probe for one API."""

    def test_minimum_is_the_gitnexus_upper_branch(self):
        self.assertEqual(integrations.NODE_MIN, (24, 11, 0))
        self.assertEqual(integrations.node_min_text(), "24.11.0")

    def test_the_minimum_itself_passes(self):
        self.assertTrue(integrations.node_version_ok("v24.11.0"))

    def test_newer_passes(self):
        for text in ("v24.11.1", "v24.14.0", "v25.0.0"):
            self.assertTrue(integrations.node_version_ok(text), text)

    def test_one_patch_below_fails(self):
        self.assertFalse(integrations.node_version_ok("v24.10.9"))

    def test_versions_gitnexus_also_rejects_fail(self):
        # 23.x and 24.0–24.10 are outside gitnexus's range as well.
        for text in ("v23.11.0", "v24.0.0", "v24.10.0"):
            self.assertFalse(integrations.node_version_ok(text), text)

    def test_the_22_line_fails_although_gitnexus_allows_part_of_it(self):
        # Deliberately stricter than `^22.18.0 || >=24.11.0`: one number to
        # state beats two ranges to explain.
        for text in ("v22.15.0", "v22.18.0", "v22.21.0"):
            self.assertFalse(integrations.node_version_ok(text), text)

    def test_a_nightly_suffix_is_read_as_its_numbers(self):
        self.assertTrue(integrations.node_version_ok("v25.0.0-nightly20260101"))
        self.assertEqual(integrations.node_version("v25.0.0-nightly1"), (25, 0, 0))

    def test_unreadable_version_is_not_ok_rather_than_silently_fine(self):
        for text in ("", "garbage", "v24.11", "v.24.11.0", "vX.Y.Z"):
            self.assertFalse(integrations.node_version_ok(text), repr(text))
            self.assertIsNone(integrations.node_version(text), repr(text))

    def test_leading_v_is_optional(self):
        self.assertEqual(integrations.node_version("24.11.0"), (24, 11, 0))


if __name__ == "__main__":
    unittest.main()
