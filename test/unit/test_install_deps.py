"""The ``--install-deps`` mode (issue #85)."""

import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_code_intel import commands, integrations


class FakeStack:
    def __init__(self, present=(), universal_ctags=True):
        self.present = set(present)
        self.universal_ctags = universal_ctags
        self.calls = []

    def have(self, name):
        return name in self.present

    def ctags_is_universal(self):
        return "ctags" in self.present and self.universal_ctags

    def brew_install(self, packages):
        self.calls.append(("brew_install", packages))
        return integrations.Exec(0, "", "")


class TtyInput(io.StringIO):
    def isatty(self):
        return True


def run(
    *,
    present=(),
    answer="",
    no_install_deps=False,
    system="Darwin",
    tty=False,
    universal_ctags=True,
):
    out, err = io.StringIO(), io.StringIO()
    stack = FakeStack(present, universal_ctags=universal_ctags)
    stdin = TtyInput(answer) if tty else io.StringIO(answer)
    code = commands.run_install_deps(
        no_install_deps=no_install_deps,
        stdout=out,
        stderr=err,
        stack=stack,
        stdin=stdin,
        system=system,
    )
    return code, out.getvalue(), err.getvalue(), stack


class InstallDeps(unittest.TestCase):
    def test_missing_tools_are_reported_and_non_tty_never_installs(self):
        code, out, err, stack = run()

        self.assertEqual(code, 1)
        self.assertEqual(err, "")
        self.assertIn("brew install", out)
        self.assertIn("ripgrep", out)
        self.assertIn("universal-ctags", out)
        self.assertIn("curl -sSL https://raw.githubusercontent.com/yoanbernabeu/grepai/main/install.sh | sh", out)
        self.assertIn("npm i -g gitnexus", out)
        self.assertEqual(stack.calls, [])

    def test_tty_confirmation_installs_only_missing_homebrew_packages(self):
        present = ("ctags", "ast-grep", "fd", "rga", "tokei", "scc", "grepai", "gitnexus")
        code, out, err, stack = run(present=present, answer="y\n", tty=True)

        self.assertEqual((code, err), (0, ""))
        self.assertIn("Install missing Homebrew packages? [y/N]", out)
        self.assertEqual(stack.calls, [("brew_install", ("ripgrep",))])

    def test_declining_confirmation_does_not_install(self):
        code, out, err, stack = run(
            present=("grepai", "gitnexus"),
            answer="n\n",
            tty=True,
        )

        self.assertEqual((code, err), (1, ""))
        self.assertIn("Install missing Homebrew packages? [y/N]", out)
        self.assertEqual(stack.calls, [])

    def test_no_install_deps_suppresses_the_offer(self):
        code, out, err, stack = run(no_install_deps=True, answer="y\n")

        self.assertEqual((code, err), (1, ""))
        self.assertNotIn("Install missing Homebrew packages? [y/N]", out)
        self.assertIn("--no-install-deps", out)
        self.assertEqual(stack.calls, [])

    def test_non_macos_prints_packages_without_brew(self):
        code, out, err, stack = run(system="Linux")

        self.assertEqual((code, err), (1, ""))
        self.assertNotIn("brew", out.lower())
        self.assertIn("Packages to install: ripgrep universal-ctags", out)
        self.assertIn("npm i -g gitnexus", out)
        self.assertEqual(stack.calls, [])

    def test_all_nine_tools_present_is_success(self):
        present = commands._INSTALL_DEPS_TOOLS
        code, out, err, stack = run(present=present)

        self.assertEqual((code, err), (0, ""))
        self.assertIn("All install dependencies are present.", out)
        self.assertNotIn("brew install", out)
        self.assertEqual(stack.calls, [])

    def test_bsd_ctags_is_offered_as_universal_ctags(self):  # issue #99
        present = commands._INSTALL_DEPS_TOOLS
        code, out, err, stack = run(present=present, universal_ctags=False)

        self.assertEqual((code, err), (1, ""))
        self.assertIn("MISSING", out)
        self.assertIn("ctags on PATH is not Universal Ctags", out)
        # The row must not claim it is absent from PATH …
        self.assertNotIn("ctags not on PATH", out)
        # … and the fix the message points at must actually offer it.
        self.assertIn("universal-ctags", out)
        self.assertNotIn("All install dependencies are present.", out)

    def test_install_hint_names_a_present_but_unusable_ctags(self):  # issue #99
        out, err = io.StringIO(), io.StringIO()
        stack = FakeStack(commands._INSTALL_DEPS_TOOLS, universal_ctags=False)

        commands.report_install_deps_hint(commands.Reporter(out, err), stack)

        self.assertIn("Missing tools: ctags", out.getvalue())
        self.assertIn("agent-code-intel --install-deps", out.getvalue())

    def test_install_hint_mentions_only_missing_tools(self):
        out, err = io.StringIO(), io.StringIO()
        stack = FakeStack(("rg", "grepai"))

        commands.report_install_deps_hint(commands.Reporter(out, err), stack)

        self.assertEqual(err.getvalue(), "")
        self.assertIn("Missing tools: ctags", out.getvalue())
        self.assertIn("gitnexus", out.getvalue())
        self.assertIn("agent-code-intel --install-deps", out.getvalue())

    def test_install_hint_is_silent_when_every_tool_is_present(self):
        out, err = io.StringIO(), io.StringIO()
        stack = FakeStack(commands._INSTALL_DEPS_TOOLS)

        commands.report_install_deps_hint(commands.Reporter(out, err), stack)

        self.assertEqual((out.getvalue(), err.getvalue()), ("", ""))


if __name__ == "__main__":
    unittest.main()
