"""Parser and early-exit unit tests — the reference's argument loop
(``9406cce`` lines 242–297), reproduced by ``agent_code_intel.cli``.

Covers ledger rows RT-1 (pipeline order), RT-2 (flag matrix), RT-3 (last mode-switch wins), RT-4
(``--help`` / ``--version`` first-wins, short-circuit right), RT-6 (unknown
flag), RT-7 (workspace twice), RT-8 (``--agent`` enum), RT-10 (``--path``
needs an argument; root defaults to cwd), RT-12 (parse error exits 1),
RT-14 (usage → stdout), FMT-1 (``die`` wording).
"""

import dataclasses
import io
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_code_intel import __version__, agent_skills
from agent_code_intel.cli import Options, USAGE, _conf_dir, main, parse_args

# main() now loads config before parsing (issue #41 §4), so it reads
# ``$HOME/.config/code-intel``. Point HOME at an empty scratch dir so every
# run resolves to the built-in defaults and never touches the real machine.
_ISO_HOME = tempfile.mkdtemp(prefix="aci-cli-parser-")


def run(argv, cwd="/work"):
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), {"HOME": _ISO_HOME}, cwd, out, err)
    return code, out.getvalue(), err.getvalue()


class EarlyExit(unittest.TestCase):
    def test_version_to_stdout_exit_0(self):
        code, out, err = run(["--version"])
        self.assertEqual((code, out, err), (0, "agent-code-intel %s\n" % __version__, ""))

    def test_help_to_stdout_exit_0(self):
        code, out, err = run(["--help"])
        self.assertEqual(code, 0)
        self.assertEqual(out, USAGE)
        self.assertEqual(err, "")

    def test_dash_h_is_help(self):
        self.assertEqual(run(["-h"])[1], USAGE)

    def test_first_early_flag_wins(self):
        self.assertEqual(run(["--version", "--help"])[1], "agent-code-intel %s\n" % __version__)
        self.assertEqual(run(["--help", "--version"])[1], USAGE)

    def test_early_flag_short_circuits_everything_to_its_right(self):
        # A bad flag to the RIGHT of --version is never reached.
        code, out, err = run(["--version", "--definitely-not-a-flag"])
        self.assertEqual((code, err), (0, ""))
        # A bad flag to the LEFT still errors — the loop reached it first.
        code, _, err = run(["--definitely-not-a-flag", "--version"])
        self.assertEqual(code, 1)
        self.assertIn("unknown flag: --definitely-not-a-flag", err)

    def test_leading_positional_then_version(self):
        self.assertEqual(run(["myws", "--version"])[0], 0)

    def test_help_after_path_is_consumed_as_the_path_argument(self):
        # --path takes the next token unconditionally; --help is not seen.
        opts = parse_args(["--path", "--help"], default_root="/work")
        self.assertEqual((opts.action, opts.root, opts.root_explicit), ("run", "--help", True))


class ParseErrors(unittest.TestCase):
    def test_unknown_long_flag(self):
        code, _, err = run(["--no-such"])
        self.assertEqual((code, err), (1, "[ERROR: unknown flag: --no-such]\n"))

    def test_unknown_short_token(self):
        for tok in ("-", "--", "-x", "-hh", "--help-me"):
            with self.subTest(tok=tok):
                code, _, err = run([tok])
                self.assertEqual((code, err), (1, "[ERROR: unknown flag: %s]\n" % tok))

    def test_version_with_equals_is_an_unknown_flag(self):
        self.assertEqual(run(["--version=foo"])[2], "[ERROR: unknown flag: --version=foo]\n")

    def test_path_requires_argument(self):
        code, _, err = run(["--path"])
        self.assertEqual((code, err), (1, "[ERROR: --path requires a directory argument]\n"))

    def test_agent_requires_argument(self):
        code, _, err = run(["--agent"])
        self.assertEqual((code, err), (1, "[ERROR: --agent requires: claude, codex or both]\n"))

    def test_agent_rejects_bad_value(self):
        code, _, err = run(["--agent", "nope"])
        self.assertEqual((code, err), (1, "[ERROR: --agent must be claude, codex or both (got 'nope')]\n"))

    def test_agent_consumes_next_token_even_if_it_looks_like_a_flag(self):
        self.assertEqual(
            run(["--agent", "--help"])[2],
            "[ERROR: --agent must be claude, codex or both (got '--help')]\n",
        )

    def test_workspace_given_twice(self):
        code, _, err = run(["foo", "bar"])
        self.assertEqual((code, err), (1, "[ERROR: workspace name given twice ('foo' and 'bar')]\n"))

    def test_empty_string_positional_does_not_count_as_taken(self):
        opts = parse_args(["", "x"], default_root="/work")
        self.assertEqual(opts.workspace, "x")


class Options_(unittest.TestCase):
    def test_defaults_match_the_reference_globals(self):
        o = parse_args([], default_root="/work")
        self.assertEqual(o.action, "run")
        self.assertEqual(o.mode, "init")
        self.assertEqual(o.root, "/work")
        self.assertFalse(o.root_explicit)
        self.assertIsNone(o.workspace)
        self.assertEqual(o.agent_target, "both")
        self.assertFalse(o.agent_explicit)
        for name in ("bootstrap", "do_git", "start_watch", "run_analyze", "write_docs",
                     "write_hook", "write_perms", "do_grepai", "do_gitnexus"):
            self.assertTrue(getattr(o, name), name)
        for name in (
            "apply",
            "force_docs",
            "status_all",
            "as_json",
            "purge_collection",
            "no_install_deps",
        ):
            self.assertFalse(getattr(o, name), name)

    def test_options_is_immutable(self):
        o = parse_args([], default_root="/work")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            o.mode = "status"  # type: ignore[misc]

    def test_path_sets_root_and_explicit_last_wins(self):
        o = parse_args(["--path", "/a", "--path", "/b"], default_root="/work")
        self.assertEqual((o.root, o.root_explicit), ("/b", True))

    def test_every_bare_boolean_flag(self):
        cases = {
            "--apply": ("apply", True),
            "--all": ("status_all", True),
            "--json": ("as_json", True),
            "--no-bootstrap": ("bootstrap", False),
            "--no-git": ("do_git", False),
            "--no-watch": ("start_watch", False),
            "--no-analyze": ("run_analyze", False),
            "--no-docs": ("write_docs", False),
            "--no-hook": ("write_hook", False),
            "--force-docs": ("force_docs", True),
            "--no-grepai": ("do_grepai", False),
            "--no-gitnexus": ("do_gitnexus", False),
            "--purge-collection": ("purge_collection", True),
            "--no-perms": ("write_perms", False),
            "--no-install-deps": ("no_install_deps", True),
        }
        for flag, (attr, want) in cases.items():
            with self.subTest(flag=flag):
                self.assertEqual(getattr(parse_args([flag], default_root="/w"), attr), want)

    def test_flags_are_idempotent_when_repeated(self):
        o = parse_args(["--apply", "--apply", "--json", "--json"], default_root="/w")
        self.assertTrue(o.apply and o.as_json)

    def test_agent_enum_accepts_all_three(self):
        for who in ("claude", "codex", "both"):
            self.assertEqual(parse_args(["--agent", who], default_root="/w").agent_target, who)

    def test_agent_records_that_it_was_given(self):
        """The default and an explicit `--agent both` are different answers:
        only the second one may override what `.code-intel` records."""
        for who in ("claude", "codex", "both"):
            self.assertTrue(
                parse_args(["--agent", who], default_root="/w").agent_explicit, who
            )

    def test_last_mode_switch_wins_no_mutual_exclusivity(self):
        self.assertEqual(parse_args(["--status", "--remove"], default_root="/w").mode, "remove")
        self.assertEqual(parse_args(["--remove", "--status"], default_root="/w").mode, "status")
        self.assertEqual(parse_args(["--refresh", "--install", "--status"], default_root="/w").mode, "status")
        self.assertEqual(parse_args(["--install-deps"], default_root="/w").mode, "install_deps")

    def test_positional_is_the_workspace(self):
        o = parse_args(["my-ws"], default_root="/w")
        self.assertEqual((o.workspace, o.workspace_explicit), ("my-ws", True))


class ConfDir(unittest.TestCase):
    """``${XDG_CONFIG_HOME:-$HOME/.config}/code-intel`` (ledger CFG-14)."""

    def test_xdg_config_home_wins(self):
        self.assertEqual(
            _conf_dir({"HOME": "/h", "XDG_CONFIG_HOME": "/xdg"}),
            "/xdg/code-intel",
        )

    def test_empty_xdg_falls_through_to_home(self):
        self.assertEqual(
            _conf_dir({"HOME": "/h", "XDG_CONFIG_HOME": ""}),
            "/h/.config/code-intel",
        )

    def test_default_is_home_dot_config(self):
        self.assertEqual(_conf_dir({"HOME": "/h"}), "/h/.config/code-intel")


class Dispatch(unittest.TestCase):
    """Config load, identity resolution, ``--install``, ``--status``,
    ``--refresh``, init preview/apply and ``--remove`` are converted
    (issues #51–#56)."""

    def test_init_runs_preflight_and_remove_is_a_noop_on_an_unconfigured_project(self):
        scratch = tempfile.mkdtemp(prefix="aci-dispatch-")
        code, out, err = run([], cwd=scratch)
        self.assertEqual(code, 1)
        self.assertIn("Preflight", out)
        self.assertIn("preflight found", err)

        code, out, err = run(["--remove"], cwd=scratch)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Nothing to remove.", out)

    def test_refresh_outside_git_fails_before_the_mode(self):
        # --refresh resolves the git root first; an empty dir is not one.
        scratch = tempfile.mkdtemp(prefix="aci-dispatch-refresh-")
        code, out, err = run(["--refresh"], cwd=scratch)
        self.assertEqual((code, out), (1, ""))
        self.assertIn("not inside a git repository", err)

    def test_refresh_is_dispatched_and_needs_no_stack_when_both_sides_skip(self):
        # `--refresh --no-grepai --no-gitnexus` is the one refresh happy path
        # that runs with nothing installed (issue #54; black-box parity with
        # test_refresh_with_both_stacks_skipped_needs_no_stack).
        scratch = tempfile.mkdtemp(prefix="aci-dispatch-refresh-ok-")
        subprocess.run(["git", "init", "-q", scratch], check=True)
        with open(os.path.join(scratch, ".code-intel"), "w") as handle:
            handle.write(
                "SCHEMA=1\nWORKSPACE=skip-ws\nPROJECT=%s\n" % os.path.basename(scratch)
            )
        agent_skills.install_targets(scratch, "both", False)
        code, out, err = run(["--refresh", "--no-grepai", "--no-gitnexus"], cwd=scratch)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Workspace: skip-ws", out)
        self.assertIn("Code intelligence is fresh.", out)


class Pipeline(unittest.TestCase):
    def test_config_parse_and_install_are_ordered_before_project_dispatch(self):  # RT-1
        events = []

        def load(*args, **kwargs):
            events.append("config")
            return mock.Mock(source="defaults", child_env={})

        def parse(*args, **kwargs):
            events.append("parse")
            return Options(mode="install")

        def install_run(**kwargs):
            events.append("install")
            return 0

        with mock.patch("agent_code_intel.cli.config.load", side_effect=load), \
             mock.patch("agent_code_intel.cli.parse_args", side_effect=parse), \
             mock.patch("agent_code_intel.cli.install.run", side_effect=install_run), \
             mock.patch("agent_code_intel.cli.project.resolve_project") as resolve:
            code = main(["--install"], {"HOME": _ISO_HOME}, "/work", io.StringIO(), io.StringIO())

        self.assertEqual(code, 0)
        self.assertEqual(events, ["config", "parse", "install"])
        resolve.assert_not_called()

    def test_project_resolution_follows_argument_parsing_for_normal_modes(self):  # RT-1
        events = []

        def load(*args, **kwargs):
            events.append("config")
            return mock.Mock(source="defaults")

        def parse(*args, **kwargs):
            events.append("parse")
            return Options(mode="status")

        def resolve(*args, **kwargs):
            events.append("resolve")
            return object()

        def status(**kwargs):
            events.append("status")
            return 0

        with mock.patch("agent_code_intel.cli.config.load", side_effect=load), \
             mock.patch("agent_code_intel.cli.parse_args", side_effect=parse), \
             mock.patch("agent_code_intel.cli.project.resolve_project", side_effect=resolve), \
             mock.patch("agent_code_intel.cli.commands.run_status", side_effect=status):
            code = main(["--status"], {"HOME": _ISO_HOME}, "/work", io.StringIO(), io.StringIO())

        self.assertEqual(code, 0)
        self.assertEqual(events, ["config", "parse", "resolve", "status"])


if __name__ == "__main__":
    unittest.main()
