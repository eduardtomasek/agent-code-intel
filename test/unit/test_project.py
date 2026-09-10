"""Project identity — canonicalisation, the strict ``.code-intel`` parser, the
workspace precedence chain, the nearest-git-root rule and the legacy
``refresh-intel.sh`` helpers (issue #51; ledger rows ID-1…ID-6, RT-13, DEV-10).
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_code_intel import project
from agent_code_intel.config import CliError


def _mkrepo(name):
    root = os.path.join(tempfile.mkdtemp(prefix="aci-proj-"), name)
    os.makedirs(root)
    subprocess.run(["git", "init", "-q", root], check=True)
    return root


def _write_code_intel(root, *lines):
    with open(os.path.join(root, ".code-intel"), "w") as handle:
        handle.write("\n".join(lines) + "\n")


class Canon(unittest.TestCase):
    def test_non_directory_returns_the_input_unchanged(self):  # TOL-7
        self.assertEqual(project.canon("/no/such/path/here"), "/no/such/path/here")

    def test_existing_directory_is_resolved_physically(self):
        real = _mkrepo("canontest")
        link = os.path.join(tempfile.mkdtemp(prefix="aci-link-"), "alias")
        os.symlink(real, link)
        self.assertEqual(project.canon(link), project.canon(real))


class ReadCodeIntel(unittest.TestCase):
    def test_absent(self):
        root = tempfile.mkdtemp(prefix="aci-proj-")
        self.assertEqual(project.read_code_intel(root).status, "ABSENT")

    def test_ok(self):
        root = _mkrepo("widget")
        _write_code_intel(root, "SCHEMA=1", "WORKSPACE=team", "PROJECT=widget")
        ident = project.read_code_intel(root)
        self.assertEqual((ident.status, ident.workspace, ident.project),
                         ("OK", "team", "widget"))

    def test_comments_and_blank_lines_are_ignored(self):
        root = _mkrepo("widget")
        _write_code_intel(root, "# hi", "", "SCHEMA=1", "WORKSPACE=team", "PROJECT=widget")
        self.assertEqual(project.read_code_intel(root).status, "OK")

    def test_value_may_contain_spaces(self):
        root = _mkrepo("CS Imager (test intel code)")
        _write_code_intel(root, "SCHEMA=1", "WORKSPACE=cs-imager",
                          "PROJECT=CS Imager (test intel code)")
        ident = project.read_code_intel(root)
        self.assertEqual((ident.status, ident.project),
                         ("OK", "CS Imager (test intel code)"))

    def test_malformed_line(self):
        root = _mkrepo("widget")
        _write_code_intel(root, "SCHEMA=1", "this is not valid", "WORKSPACE=t", "PROJECT=widget")
        ident = project.read_code_intel(root)
        self.assertEqual(ident.status, "ERR")
        self.assertIn("malformed line", ident.message)

    def test_unknown_key(self):
        root = _mkrepo("widget")
        _write_code_intel(root, "SCHEMA=1", "WORKSPACE=t", "PROJECT=widget", "EXTRA=x")
        self.assertIn("unknown key 'EXTRA'", project.read_code_intel(root).message)

    def test_duplicate_key(self):
        root = _mkrepo("widget")
        _write_code_intel(root, "SCHEMA=1", "WORKSPACE=a", "WORKSPACE=b", "PROJECT=widget")
        self.assertIn("duplicate key 'WORKSPACE'", project.read_code_intel(root).message)

    def test_missing_required_key(self):
        root = _mkrepo("widget")
        _write_code_intel(root, "SCHEMA=1", "WORKSPACE=t")
        self.assertIn("missing required key PROJECT", project.read_code_intel(root).message)

    def test_unsupported_schema(self):
        root = _mkrepo("widget")
        _write_code_intel(root, "SCHEMA=3", "WORKSPACE=t", "PROJECT=widget")
        self.assertIn("unsupported SCHEMA=3", project.read_code_intel(root).message)

    def test_project_must_match_the_directory_name(self):
        root = _mkrepo("widget")
        _write_code_intel(root, "SCHEMA=1", "WORKSPACE=t", "PROJECT=gadget")
        self.assertIn("says PROJECT=gadget", project.read_code_intel(root).message)

    def test_it_never_executes_the_file(self):
        root = _mkrepo("widget")
        marker = os.path.join(root, "PWNED")
        _write_code_intel(root, "SCHEMA=1", "WORKSPACE=t", "PROJECT=widget",
                          "$(touch %s)" % marker)
        project.read_code_intel(root)
        self.assertFalse(os.path.exists(marker))


class Slug(unittest.TestCase):
    def test_lowercases_and_dashes_non_alphanumerics(self):
        self.assertEqual(project.slug("My Project!"), "my-project")

    def test_collapses_and_trims_dashes(self):
        self.assertEqual(project.slug("--a..b--"), "a-b")


class ManagedDocs(unittest.TestCase):
    def test_current_block_is_noop_and_stale_block_converges(self):
        root = tempfile.mkdtemp(prefix="aci-doc-")
        path = os.path.join(root, "AGENTS.md")
        old = "<!-- code-intel:start -->old<!-- code-intel:end -->"
        current = "<!-- code-intel:start -->current<!-- code-intel:end -->"
        Path(path).write_text("before\n" + old + "\nafter\n")

        message, changed = project.write_managed_doc(path, current, False)
        self.assertEqual(
            (message, changed), ("code-intel block rewritten in place", True)
        )
        self.assertEqual(Path(path).read_text(), "before\n" + current + "\nafter\n")

        before = os.stat(path).st_mtime_ns
        message, changed = project.write_managed_doc(path, current, False)
        self.assertEqual((message, changed), ("code-intel block already present", False))
        self.assertEqual(os.stat(path).st_mtime_ns, before)

    def test_current_block_preserves_a_foreign_block(self):
        root = tempfile.mkdtemp(prefix="aci-doc-foreign-")
        path = os.path.join(root, "AGENTS.md")
        foreign = "<!-- other-tool:start -->foreign<!-- other-tool:end -->"
        current = "<!-- code-intel:start -->current<!-- code-intel:end -->"
        expected = "before\n" + foreign + "\n" + current + "\nafter\n"
        Path(path).write_text(expected)

        before = os.stat(path).st_mtime_ns
        message, changed = project.write_managed_doc(path, current, False)

        self.assertEqual((message, changed), ("code-intel block already present", False))
        self.assertEqual(Path(path).read_text(), expected)
        self.assertEqual(os.stat(path).st_mtime_ns, before)


class ResolveProject(unittest.TestCase):
    def _resolve(self, **kw):
        defaults = dict(root_explicit=False, mode="init", workspace=None,
                        home="/nonexistent-home", status_all=False)
        defaults.update(kw)
        return project.resolve_project(**defaults)

    def test_explicit_workspace_wins_over_code_intel(self):  # ID-2
        root = _mkrepo("widget")
        _write_code_intel(root, "SCHEMA=1", "WORKSPACE=fromfile", "PROJECT=widget")
        ctx = self._resolve(root=root, workspace="explicit")
        self.assertEqual(ctx.workspace, "explicit")
        self.assertEqual(ctx.proj_name, "widget")

    def test_code_intel_workspace_used_when_no_argument(self):
        root = _mkrepo("widget")
        _write_code_intel(root, "SCHEMA=1", "WORKSPACE=fromfile", "PROJECT=widget")
        self.assertEqual(self._resolve(root=root).workspace, "fromfile")

    def test_absent_falls_back_to_the_basename_slug(self):  # ID-2, DEV-10
        root = os.path.join(tempfile.mkdtemp(prefix="aci-proj-"), "My.Repo")
        os.makedirs(root)
        ctx = self._resolve(root=root)
        self.assertEqual(ctx.workspace, "my-repo")  # WS sanitized
        self.assertEqual(ctx.proj_name, "My.Repo")  # PROJ_NAME raw

    def test_broken_code_intel_is_fatal(self):  # ID-1
        root = _mkrepo("widget")
        _write_code_intel(root, "SCHEMA=9", "WORKSPACE=t", "PROJECT=widget")
        with self.assertRaises(CliError) as caught:
            self._resolve(root=root)
        self.assertIn("unsupported SCHEMA=9", str(caught.exception))

    def test_not_a_directory(self):
        with self.assertRaises(CliError) as caught:
            self._resolve(root="/no/such/dir/anywhere")
        self.assertIn("not a directory", str(caught.exception))

    def test_refresh_resolves_the_nearest_git_root(self):  # ID-3
        root = _mkrepo("outer")
        nested = os.path.join(root, "sub", "inner")
        os.makedirs(nested)
        _write_code_intel(root, "SCHEMA=1", "WORKSPACE=outerws", "PROJECT=outer")
        ctx = project.resolve_project(
            root=nested, root_explicit=False, mode="refresh", workspace=None,
            home="/nonexistent-home", status_all=False,
        )
        self.assertEqual(ctx.workspace, "outerws")
        self.assertEqual(project.canon(ctx.root), project.canon(root))

    def test_refresh_outside_a_git_repo_is_fatal(self):  # ID-3 / REF-6
        plain = tempfile.mkdtemp(prefix="aci-nogit-")
        with self.assertRaises(CliError) as caught:
            project.resolve_project(
                root=plain, root_explicit=False, mode="refresh", workspace=None,
                home="/nonexistent-home", status_all=False,
            )
        self.assertIn("not inside a git repository", str(caught.exception))

    def test_refresh_with_explicit_path_skips_the_git_root_search(self):  # ID-4
        plain = tempfile.mkdtemp(prefix="aci-nogit-")
        os.rename(plain, plain + "-x")
        plain = plain + "-x"
        _write_code_intel(plain, "SCHEMA=1", "WORKSPACE=w", "PROJECT=%s" % os.path.basename(plain))
        ctx = project.resolve_project(
            root=plain, root_explicit=True, mode="refresh", workspace=None,
            home="/nonexistent-home", status_all=False,
        )
        self.assertEqual(ctx.workspace, "w")

    def test_refresh_never_bootstraps_an_absent_project(self):  # REF-1
        root = _mkrepo("fresh")
        with self.assertRaises(CliError) as caught:
            project.resolve_project(
                root=root, root_explicit=True, mode="refresh", workspace=None,
                home="/nonexistent-home", status_all=False,
            )
        self.assertIn("this project has not been set up", str(caught.exception))

    def test_home_guard_blocks_running_over_home(self):  # ID-6
        home = _mkrepo("home")
        with self.assertRaises(CliError) as caught:
            project.resolve_project(
                root=home, root_explicit=True, mode="init", workspace=None,
                home=home, status_all=False,
            )
        self.assertIn("refusing to run over your home directory", str(caught.exception))

    def test_guard_blocks_a_directory_that_contains_home(self):  # ID-6
        parent = _mkrepo("parent")
        home = os.path.join(parent, "me")
        os.makedirs(home)
        with self.assertRaises(CliError) as caught:
            project.resolve_project(
                root=parent, root_explicit=True, mode="init", workspace=None,
                home=home, status_all=False,
            )
        self.assertIn("it contains your home directory", str(caught.exception))

    def test_guard_blocks_the_filesystem_root(self):  # ID-6
        with self.assertRaises(CliError) as caught:
            project.resolve_project(
                root="/", root_explicit=True, mode="init", workspace=None,
                home="/root", status_all=False,
            )
        self.assertIn("filesystem root", str(caught.exception))

    def test_home_guard_is_skipped_for_status_all(self):  # ID-6
        home = _mkrepo("home")
        _write_code_intel(home, "SCHEMA=1", "WORKSPACE=hw", "PROJECT=home")
        ctx = project.resolve_project(
            root=home, root_explicit=True, mode="status", workspace=None,
            home=home, status_all=True,
        )
        self.assertEqual(ctx.workspace, "hw")

    def test_context_is_immutable(self):
        root = _mkrepo("widget")
        ctx = self._resolve(root=root)
        with self.assertRaises(Exception):
            ctx.workspace = "x"  # type: ignore[misc]


_LEGACY_FIXTURE = str(
    Path(__file__).resolve().parents[1] / "lib" / "legacy_refresh_fixture.py"
)


class Legacy(unittest.TestCase):
    def _pristine(self, ws):
        # Build through the shared Python fixture. Production still supports
        # migrating this legacy file, but the frozen Bash reference does not.
        d = tempfile.mkdtemp(prefix="aci-legacy-")
        subprocess.run(
            [sys.executable, _LEGACY_FIXTURE, "pristine", d, ws],
            check=True,
        )
        return os.path.join(d, "refresh-intel.sh")

    def test_pristine_script_is_recognised(self):
        path = self._pristine("legacyws")
        self.assertTrue(project.legacy_refresh_is_pristine(path))
        self.assertEqual(project.read_legacy_workspace(path), "legacyws")

    def test_hand_modified_script_is_rejected(self):
        path = self._pristine("legacyws")
        with open(path, "a") as handle:
            handle.write("\n# tampered\n")
        self.assertFalse(project.legacy_refresh_is_pristine(path))

    def test_adopt_uses_the_legacy_workspace(self):
        self.assertEqual(
            project.adopt_legacy_workspace(None, False, "legacyws", "/x/refresh-intel.sh"),
            "legacyws",
        )

    def test_adopt_conflict_with_explicit_workspace_is_fatal(self):
        with self.assertRaises(CliError) as caught:
            project.adopt_legacy_workspace("mine", True, "legacyws", "/x/refresh-intel.sh")
        self.assertIn("conflicts with 'legacyws'", str(caught.exception))

    def test_adopt_allows_matching_explicit_workspace(self):
        self.assertEqual(
            project.adopt_legacy_workspace("legacyws", True, "legacyws", "/x/refresh-intel.sh"),
            "legacyws",
        )


class AgentsKey(unittest.TestCase):
    """``AGENTS`` in ``.code-intel`` (schema 2) and the schema-1 files that
    predate it. The key is what makes a project answer for itself instead of
    being audited against whatever default the command line carries."""

    def test_schema_2_records_the_agents(self):
        root = _mkrepo("widget")
        _write_code_intel(
            root, "SCHEMA=2", "WORKSPACE=team", "PROJECT=widget", "AGENTS=claude"
        )
        ident = project.read_code_intel(root)
        self.assertEqual(ident.status, "OK")
        self.assertEqual(ident.agents, "claude")

    def test_schema_1_stays_readable_and_says_nothing(self):
        root = _mkrepo("widget")
        _write_code_intel(root, "SCHEMA=1", "WORKSPACE=team", "PROJECT=widget")
        ident = project.read_code_intel(root)
        self.assertEqual(ident.status, "OK")
        self.assertIsNone(ident.agents)

    def test_schema_2_without_agents_is_an_error(self):
        root = _mkrepo("widget")
        _write_code_intel(root, "SCHEMA=2", "WORKSPACE=team", "PROJECT=widget")
        self.assertIn(
            "missing required key AGENTS", project.read_code_intel(root).message
        )

    def test_unknown_agent_value_is_an_error(self):
        root = _mkrepo("widget")
        _write_code_intel(
            root, "SCHEMA=2", "WORKSPACE=team", "PROJECT=widget", "AGENTS=emacs"
        )
        self.assertIn("AGENTS=emacs is not one of", project.read_code_intel(root).message)

    def test_agents_is_honoured_under_schema_1_too(self):
        """A hand-written key is read, not rejected: the value is what matters,
        and refusing it would only send the user to edit the file again."""
        root = _mkrepo("widget")
        _write_code_intel(
            root, "SCHEMA=1", "WORKSPACE=team", "PROJECT=widget", "AGENTS=codex"
        )
        self.assertEqual(project.read_code_intel(root).agents, "codex")


class WriteIdentity(unittest.TestCase):
    def test_written_file_reads_back_at_the_current_schema(self):
        root = _mkrepo("widget")
        project.write_identity(root, "team", "widget", "claude")
        ident = project.read_code_intel(root)
        self.assertEqual((ident.status, ident.workspace, ident.agents),
                         ("OK", "team", "claude"))
        with open(os.path.join(root, ".code-intel")) as handle:
            body = handle.read()
        self.assertIn("SCHEMA=2\n", body)
        self.assertIn("AGENTS=claude\n", body)
        self.assertTrue(body.startswith("# agent-code-intel"))

    def test_rewriting_replaces_the_recorded_agents(self):
        root = _mkrepo("widget")
        project.write_identity(root, "team", "widget", "both")
        project.write_identity(root, "team", "widget", "claude")
        self.assertEqual(project.read_code_intel(root).agents, "claude")

    def test_an_unknown_value_is_refused_before_it_reaches_the_file(self):
        root = _mkrepo("widget")
        with self.assertRaises(CliError):
            project.write_identity(root, "team", "widget", "emacs")
        self.assertFalse(os.path.exists(os.path.join(root, ".code-intel")))


class EffectiveAgents(unittest.TestCase):
    def test_the_recorded_value_wins_over_the_default(self):
        self.assertEqual(project.effective_agents("claude", "both", False), "claude")

    def test_an_explicit_flag_wins_over_the_recorded_value(self):
        self.assertEqual(project.effective_agents("claude", "codex", True), "codex")

    def test_an_unrecorded_project_keeps_the_command_line_default(self):
        self.assertEqual(project.effective_agents(None, "both", False), "both")


class IdentityCurrent(unittest.TestCase):
    def _context(self, root, agents):
        return project.ProjectContext(
            root=root,
            workspace="team",
            proj_name=os.path.basename(root),
            grepai_cfg="",
            mcp_json="",
            refresh_script="",
            ident_status="OK",
            ident_workspace="team",
            ident_project=os.path.basename(root),
            ident_agents=agents,
        )

    def test_matching_agents_is_current(self):
        context = self._context("/x/widget", "claude")
        self.assertTrue(project.identity_current(context, "claude"))

    def test_different_agents_is_not_current(self):
        context = self._context("/x/widget", "claude")
        self.assertFalse(project.identity_current(context, "both"))

    def test_a_schema_1_file_is_never_current(self):
        context = self._context("/x/widget", None)
        self.assertFalse(project.identity_current(context, "both"))


if __name__ == "__main__":
    unittest.main()
