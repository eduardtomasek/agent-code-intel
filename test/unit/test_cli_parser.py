"""Parser and early-exit unit tests — the reference's argument loop
(``9406cce`` lines 242–297), reproduced by ``agent_code_intel.cli``.

Covers ledger rows RT-2 (flag matrix), RT-3 (last mode-switch wins), RT-4
(``--help`` / ``--version`` first-wins, short-circuit right), RT-6 (unknown
flag), RT-7 (workspace twice), RT-8 (``--agent`` enum), RT-10 (``--path``
needs an argument; root defaults to cwd), RT-12 (parse error exits 1),
RT-14 (usage → stdout), FMT-1 (``die`` wording).
"""

import dataclasses
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_code_intel import __version__
from agent_code_intel.cli import USAGE, _conf_dir, main, parse_args

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
        for name in ("bootstrap", "do_git", "start_watch", "run_analyze", "write_docs",
                     "write_perms", "do_grepai", "do_gitnexus"):
            self.assertTrue(getattr(o, name), name)
        for name in ("apply", "force_docs", "status_all", "as_json", "purge_collection"):
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
            "--force-docs": ("force_docs", True),
            "--no-grepai": ("do_grepai", False),
            "--no-gitnexus": ("do_gitnexus", False),
            "--purge-collection": ("purge_collection", True),
            "--no-perms": ("write_perms", False),
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

    def test_last_mode_switch_wins_no_mutual_exclusivity(self):
        self.assertEqual(parse_args(["--status", "--remove"], default_root="/w").mode, "remove")
        self.assertEqual(parse_args(["--remove", "--status"], default_root="/w").mode, "status")
        self.assertEqual(parse_args(["--refresh", "--install", "--status"], default_root="/w").mode, "status")

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
    """Config load and identity resolution are converted (issue #51); the
    modes themselves are not, and a resolved mode must not report success
    (issue #48, decision 70)."""

    def test_no_mode_is_faked_green(self):
        scratch = tempfile.mkdtemp(prefix="aci-dispatch-")
        for argv, needle in (
            ([], "'init' mode"),
            (["--status"], "'status' mode"),
            (["--status", "--json"], "'status-json' mode"),
            (["--remove"], "'remove' mode"),
            (["--install"], "'install' mode"),
        ):
            with self.subTest(argv=argv):
                code, out, err = run(argv, cwd=scratch)
                self.assertEqual(code, 1)
                self.assertEqual(out, "")
                self.assertTrue(err.startswith("[ERROR: "))
                self.assertIn(needle, err)

    def test_refresh_outside_git_fails_before_the_mode(self):
        # --refresh resolves the git root first; an empty dir is not one.
        scratch = tempfile.mkdtemp(prefix="aci-dispatch-refresh-")
        code, out, err = run(["--refresh"], cwd=scratch)
        self.assertEqual((code, out), (1, ""))
        self.assertIn("not inside a git repository", err)


if __name__ == "__main__":
    unittest.main()
