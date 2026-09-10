"""Preview/apply orchestration for issue #55."""

import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_code_intel import agent_skills, commands, hooks, integrations, project
from agent_code_intel.config import ChildEnvironment, LoadedConfig, default_config
from agent_code_intel.project import ProjectContext


class FakeStack:
    def __init__(self, present=()):
        self.present = set(present or ("grepai", "gitnexus", "curl", "git", "claude", "codex", "ollama"))
        self.calls = []
        self.workspace = False
        # A present ctags is a working one unless a test says otherwise
        # (issue #99).
        self.universal_ctags = True

    def have(self, name):
        self.calls.append(("have", name))
        return name in self.present

    def ctags_is_universal(self):
        return "ctags" in self.present and self.universal_ctags

    def first_line(self, *argv):
        if argv == ("node", "--version"):
            return "v24.11.0"
        return "gitnexus 9.9.9"

    def gitnexus_runs(self):
        return True

    def node_has_register_hooks(self):
        return True

    def node_version_ok(self):
        # The real gate over the faked `node --version`, so a stack that fakes
        # an old node reports what production would report.
        return "node" in self.present and integrations.node_version_ok(
            self.first_line("node", "--version")
        )

    def qdrant_http_ok(self, url):
        return True

    def qdrant_grpc_ok(self, host, port):
        return True

    def container_cli(self):
        return ""

    def container_daemon_ok(self, cli):
        return False

    def ollama_up(self):
        return True

    def ollama_has_model(self, model):
        return True

    def ws_show(self, workspace):
        return "" if not self.workspace else "  - project: /tmp/project\n  model nomic-embed-text-v2-moe\n"

    def ws_exists(self, workspace):
        self.calls.append(("ws_exists", workspace))
        return self.workspace

    def watch_status(self, workspace):
        return "not running"

    def git_is_repo(self, cwd):
        self.calls.append(("git_is_repo", cwd))
        return os.path.isdir(os.path.join(cwd, ".git"))

    def git_init(self, cwd):
        self.calls.append(("git_init", cwd))
        subprocess.run(["git", "init", "-q", cwd], check=True)
        return integrations.Exec(0, "", "")

    def workspace_create(self, *args):
        self.calls.append(("workspace_create",) + args)
        self.workspace = True
        return integrations.Exec(0, "", "")

    def workspace_add(self, *args):
        self.calls.append(("workspace_add",) + args)
        return integrations.Exec(0, "", "")

    def grepai_init(self, root, provider, model):
        self.calls.append(("grepai_init", root, provider, model))
        os.makedirs(os.path.dirname(os.path.join(root, ".grepai", "config.yaml")), exist_ok=True)
        with open(os.path.join(root, ".grepai", "config.yaml"), "w") as handle:
            handle.write("chunking:\n  size: 512\n  overlap: 50\nignore:\n")
        return integrations.Exec(0, "", "")

    def watch_stop(self, workspace):
        self.calls.append(("watch_stop", workspace))
        return integrations.Exec(0, "", "")

    def watch_start_background(self, workspace):
        self.calls.append(("watch_start_background", workspace))
        return integrations.Exec(0, "", "")

    def claude_mcp_get(self, name, scope):
        return integrations.Exec(1, "", "")

    def claude_mcp_add(self, *args):
        self.calls.append(("claude_mcp_add",) + args)
        return integrations.Exec(0, "", "")

    def codex_mcp_get(self, name):
        return integrations.Exec(1, "", "")

    def codex_mcp_add(self, *args):
        self.calls.append(("codex_mcp_add",) + args)
        return integrations.Exec(0, "", "")

    def gitnexus_status(self, cwd):
        return "index is up-to-date"

    def gitnexus_analyze_embeddings(self, cwd):
        self.calls.append(("gitnexus_analyze_embeddings", cwd))
        return integrations.Exec(0, "analyzed", "")


class FailingWatchStack(FakeStack):
    def watch_start_background(self, workspace):
        self.calls.append(("watch_start_background", workspace))
        return integrations.Exec(1, "", "watcher failed")


class FailingRestartStack(FakeStack):
    def watch_status(self, workspace):
        return "watcher running"

    def watch_start_background(self, workspace):
        self.calls.append(("watch_start_background", workspace))
        return integrations.Exec(1, "", "watcher restart failed")


class FailingOllamaStack(FakeStack):
    def ollama_up(self):
        return False

    def ollama_serve_background(self):
        return integrations.Exec(1, "", "ollama spawn failed")


class OldNodeStack(FakeStack):
    def node_has_register_hooks(self):
        return False

    def first_line(self, *argv):
        if argv == ("node", "--version"):
            return "v20.0.0"
        return super().first_line(*argv)


def make_context(root):
    return ProjectContext(
        root=root,
        workspace="demo",
        proj_name=os.path.basename(root),
        grepai_cfg=os.path.join(root, ".grepai", "config.yaml"),
        mcp_json=os.path.join(root, ".mcp.json"),
        refresh_script=os.path.join(root, "refresh-intel.sh"),
        ident_status="ABSENT",
        ident_workspace=None,
        ident_project=None,
    )


def loaded():
    return LoadedConfig(
        config=default_config(),
        child_env=ChildEnvironment({"PATH": ""}),
        config_file="/tmp/defaults.toml",
        source="defaults",
    )


class Init(unittest.TestCase):
    def test_apply_routes_documents_and_skills_to_selected_agents(self):
        for target, expected in (
            ("claude", {"claude"}),
            ("codex", {"codex"}),
            ("both", {"claude", "codex"}),
        ):
            with self.subTest(target=target):
                root = tempfile.mkdtemp(prefix="aci-init-agents-")
                code = commands.run_init(
                    apply=True,
                    bootstrap=False,
                    do_git=False,
                    start_watch=False,
                    run_analyze=False,
                    write_docs=True,
                    force_docs=False,
                    agent_target=target,
                    context=make_context(root),
                    loaded=loaded(),
                    conf_dir=os.path.join(root, "config"),
                    stdout=io.StringIO(),
                    stderr=io.StringIO(),
                    stack=FakeStack(),
                )

                self.assertEqual(code, 0)
                for agent, doc in (("claude", "CLAUDE.md"), ("codex", "AGENTS.md")):
                    for skill_name in agent_skills.SKILLS:
                        skill = agent_skills.target_paths(root, agent, skill_name)[0][1]
                        self.assertEqual(os.path.isfile(skill), agent in expected)
                    self.assertEqual(
                        os.path.isfile(os.path.join(root, doc)), agent in expected
                    )
                self.assertEqual(
                    os.path.isfile(os.path.join(root, hooks.SCRIPT_RELATIVE)),
                    bool(expected),
                )
                self.assertEqual(
                    os.path.isfile(os.path.join(root, hooks.SETTINGS_RELATIVE)),
                    "claude" in expected,
                )
                self.assertEqual(
                    os.path.isfile(os.path.join(root, hooks.CODEX_SETTINGS_RELATIVE)),
                    "codex" in expected,
                )

    def test_no_hook_skips_repo_local_hook(self):
        root = tempfile.mkdtemp(prefix="aci-init-no-hook-")
        code = commands.run_init(
            apply=True,
            bootstrap=False,
            do_git=False,
            start_watch=False,
            run_analyze=False,
            write_docs=False,
            write_hook=False,
            force_docs=False,
            agent_target="both",
            context=make_context(root),
            loaded=loaded(),
            conf_dir=os.path.join(root, "config"),
            stdout=io.StringIO(),
            stderr=io.StringIO(),
            stack=FakeStack(),
        )
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(os.path.join(root, hooks.SCRIPT_RELATIVE)))
        self.assertFalse(os.path.exists(os.path.join(root, hooks.SETTINGS_RELATIVE)))
        self.assertFalse(
            os.path.exists(os.path.join(root, hooks.CODEX_SETTINGS_RELATIVE))
        )

    def test_codex_hook_notice_only_appears_when_registration_changes(self):
        root = tempfile.mkdtemp(prefix="aci-init-codex-hook-")

        def apply_once():
            out, err = io.StringIO(), io.StringIO()
            code = commands.run_init(
                apply=True,
                bootstrap=False,
                do_git=False,
                start_watch=False,
                run_analyze=False,
                write_docs=False,
                write_hook=True,
                force_docs=False,
                agent_target="codex",
                context=make_context(root),
                loaded=loaded(),
                conf_dir=os.path.join(root, "config"),
                stdout=out,
                stderr=err,
                stack=FakeStack(),
            )
            return code, out.getvalue(), err.getvalue()

        code, out, err = apply_once()

        self.assertEqual((code, err), (0, ""))
        self.assertIn("codex: zapsán .codex/hooks.json", out)
        self.assertIn(
            "1) ověř, že v ~/.codex/config.toml NENÍ [features] hooks = false", out
        )
        self.assertIn("2) otevři projekt v Codexu a potvrď důvěru projektu", out)
        self.assertIn("3) spusť /hooks a hook schval", out)
        self.assertNotIn(".claude/settings.json", out)
        self.assertFalse(os.path.exists(os.path.join(root, hooks.SETTINGS_RELATIVE)))

        _, second_out, second_err = apply_once()
        self.assertEqual(second_err, "")
        self.assertNotIn("codex: zapsán .codex/hooks.json", second_out)
        self.assertNotIn("1) ověř, že v ~/.codex/config.toml NENÍ", second_out)

        Path(root, hooks.SCRIPT_RELATIVE).write_text("script changed\n")
        _, script_out, script_err = apply_once()
        self.assertEqual(script_err, "")
        self.assertNotIn("codex: zapsán .codex/hooks.json", script_out)

    def test_foreign_routing_skill_blocks_apply_before_project_mutation(self):
        root = tempfile.mkdtemp(prefix="aci-init-foreign-skill-")
        skill = agent_skills.target_paths(root, "codex")[0][1]
        os.makedirs(os.path.dirname(skill))
        Path(skill).write_text("foreign\n")
        stack = FakeStack()

        with self.assertRaises(commands.CliError):
            commands.run_init(
                apply=True,
                bootstrap=False,
                do_git=False,
                start_watch=False,
                run_analyze=False,
                write_docs=True,
                force_docs=False,
                agent_target="codex",
                context=make_context(root),
                loaded=loaded(),
                conf_dir=os.path.join(root, "config"),
                stdout=io.StringIO(),
                stderr=io.StringIO(),
                stack=stack,
            )

        self.assertEqual(Path(skill).read_text(), "foreign\n")
        self.assertFalse(os.path.exists(os.path.join(root, ".code-intel")))
        self.assertNotIn("workspace_create", [call[0] for call in stack.calls])

    def test_old_node_is_a_warning_not_a_missing_dependency(self):  # TOL-8
        root = tempfile.mkdtemp(prefix="aci-init-old-node-")
        out, err = io.StringIO(), io.StringIO()
        stack = OldNodeStack(
            present=("grepai", "gitnexus", "curl", "git", "node", "claude", "codex", "ollama")
        )

        commands._init_preflight(
            commands.Reporter(out, err),
            bootstrap=False,
            agent_target="both",
            context=make_context(root),
            config=default_config(),
            stack=stack,
        )

        self.assertIn(
            "  warn      node v20.0.0 is below the 24.11.0 that gitnexus requires",
            out.getvalue(),
        )
        self.assertNotIn("MISSING   node", out.getvalue())
        self.assertEqual(err.getvalue(), "")

    def test_code_context_tools_are_warnings_not_apply_dependencies(self):
        root = tempfile.mkdtemp(prefix="aci-init-code-context-tools-")
        out, err = io.StringIO(), io.StringIO()

        commands._init_preflight(
            commands.Reporter(out, err),
            bootstrap=False,
            agent_target="both",
            context=make_context(root),
            config=default_config(),
            stack=FakeStack(),
        )

        text = out.getvalue()
        for tool in ("rg", "ctags", "ast-grep", "fd", "rga", "tokei", "scc"):
            self.assertIn("warn      %s not on PATH" % tool, text)
        self.assertIn("ctags and ast-grep are both missing", text)
        self.assertIn("agent-code-intel --install-deps", text)
        self.assertEqual(err.getvalue(), "")

    def test_preview_runs_preflight_and_writes_no_project_files(self):
        root = tempfile.mkdtemp(prefix="aci-init-preview-")
        subprocess.run(["git", "init", "-q", root], check=True)
        stack = FakeStack()
        out, err = io.StringIO(), io.StringIO()
        code = commands.run_init(
            apply=False,
            bootstrap=False,
            do_git=True,
            start_watch=False,
            run_analyze=False,
            write_docs=False,
            force_docs=False,
            agent_target="both",
            context=make_context(root),
            loaded=loaded(),
            conf_dir=os.path.join(root, "home", ".config", "code-intel"),
            stdout=out,
            stderr=err,
            stack=stack,
        )
        self.assertEqual(code, 2)
        self.assertIn("PREVIEW — services may be started during preflight", out.getvalue())
        self.assertNotIn("no changes will be made", out.getvalue())
        self.assertFalse(os.path.exists(os.path.join(root, ".code-intel")))
        self.assertEqual(err.getvalue(), "")

    def test_apply_keeps_mutation_order_and_writes_identity_without_git(self):
        root = tempfile.mkdtemp(prefix="aci-init-apply-")
        stack = FakeStack()
        out, err = io.StringIO(), io.StringIO()
        code = commands.run_init(
            apply=True,
            bootstrap=False,
            do_git=False,
            start_watch=False,
            run_analyze=False,
            write_docs=False,
            force_docs=False,
            agent_target="both",
            context=make_context(root),
            loaded=loaded(),
            conf_dir=os.path.join(root, "home", ".config", "code-intel"),
            stdout=out,
            stderr=err,
            stack=stack,
        )
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(os.path.join(root, ".code-intel")))
        names = [call[0] for call in stack.calls]
        self.assertLess(names.index("workspace_create"), names.index("workspace_add"))
        self.assertLess(names.index("workspace_add"), names.index("grepai_init"))
        self.assertIn("skipped git (--no-git)", out.getvalue())
        self.assertFalse(os.path.exists(os.path.join(root, "CLAUDE.md")))
        self.assertFalse(os.path.exists(os.path.join(root, "AGENTS.md")))
        statuses = agent_skills.status(root, "both")
        for agent in ("claude", "codex"):
            for skill in agent_skills.SKILLS:
                self.assertEqual(statuses[agent][skill]["state"], "missing")
        self.assertEqual(err.getvalue(), "")

    def test_apply_fails_if_watcher_start_fails(self):
        root = tempfile.mkdtemp(prefix="aci-init-watch-")
        with self.assertRaises(commands.CliError):
            commands.run_init(
                apply=True,
                bootstrap=False,
                do_git=False,
                start_watch=True,
                run_analyze=False,
                write_docs=False,
                force_docs=False,
                agent_target="both",
                context=make_context(root),
                loaded=loaded(),
                conf_dir=os.path.join(root, "home", ".config", "code-intel"),
                stdout=io.StringIO(),
                stderr=io.StringIO(),
                stack=FailingWatchStack(),
            )

    def test_apply_fails_if_config_change_cannot_restart_watcher(self):
        root = tempfile.mkdtemp(prefix="aci-init-restart-")
        with self.assertRaises(commands.CliError):
            commands.run_init(
                apply=True,
                bootstrap=False,
                do_git=False,
                start_watch=False,
                run_analyze=False,
                write_docs=False,
                force_docs=False,
                agent_target="both",
                context=make_context(root),
                loaded=loaded(),
                conf_dir=os.path.join(root, "home", ".config", "code-intel"),
                stdout=io.StringIO(),
                stderr=io.StringIO(),
                stack=FailingRestartStack(),
            )

    def test_orphaned_managed_doc_is_a_fatal_error(self):
        root = tempfile.mkdtemp(prefix="aci-init-doc-")
        path = os.path.join(root, "CLAUDE.md")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("<!-- code-intel:start -->\n")
        with self.assertRaises(commands.CliError):
            commands._write_doc(commands.Reporter(io.StringIO(), io.StringIO()), path, False)

    def test_missing_owned_yaml_block_is_not_reported_as_fixed(self):
        root = tempfile.mkdtemp(prefix="aci-init-yaml-")
        path = os.path.join(root, "config.yaml")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("foreign: keep\n")
        with self.assertRaises(ValueError):
            project.update_grepai_config(path, "256", "25", ("*.lock",))

    def test_ollama_spawn_failure_does_not_wait_for_a_server(self):
        self.assertFalse(
            commands._ensure_ollama(
                commands.Reporter(io.StringIO(), io.StringIO()),
                True,
                default_config(),
                FailingOllamaStack(),
            )
        )

    def test_managed_doc_blocks_include_exact_code_context_instruction(self):
        expected = (
            "Before reading a source file, use the `code-context` skill: derive the exact\n"
            "definition range with `ctags` instead of guessing a line window, and use\n"
            "`rg`/`ast-grep` — not the knowledge graphs — for exhaustive reference lists."
        )

        self.assertEqual(set(commands._DOC_BLOCKS), {"CLAUDE.md", "AGENTS.md"})
        for block in commands._DOC_BLOCKS.values():
            self.assertEqual(block.count(expected), 1)

    def test_apply_ignores_ds_store_alongside_the_index_directories(self):
        root = tempfile.mkdtemp(prefix="aci-init-dsstore-")
        stack = FakeStack()
        stack.workspace = True

        code = commands.run_init(
            apply=True,
            bootstrap=False,
            do_git=True,
            start_watch=False,
            run_analyze=False,
            write_docs=False,
            force_docs=False,
            agent_target="both",
            context=make_context(root),
            loaded=loaded(),
            conf_dir=os.path.join(root, "config"),
            stdout=io.StringIO(),
            stderr=io.StringIO(),
            stack=stack,
        )

        self.assertEqual(code, 0)
        lines = Path(root, ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines, [".grepai/", ".gitnexus/", ".DS_Store"])

    def test_ensure_gitignore_appends_only_what_is_missing(self):
        # A hand-maintained .gitignore keeps its own lines and its order; only
        # the absent entries are appended. This is what lets a user add
        # .DS_Store by hand on an older project without --apply fighting it.
        root = tempfile.mkdtemp(prefix="aci-gitignore-append-")
        path = os.path.join(root, ".gitignore")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("node_modules/\n.DS_Store\n")

        stdout = io.StringIO()
        commands._ensure_gitignore(
            commands.Reporter(stdout, io.StringIO()),
            root,
            default_config().gitignore_entries,
        )

        lines = Path(path).read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines, ["node_modules/", ".DS_Store", ".grepai/", ".gitnexus/"])
        self.assertIn(".gitignore += .grepai/ .gitnexus/", stdout.getvalue())


class RecordsTheAgents(unittest.TestCase):
    """``--apply`` writes what it set the project up for into ``.code-intel``,
    so no later run has to be told again (and none has to guess ``both``)."""

    def _apply(self, root, agent_target, context=None, agent_explicit=False):
        out = io.StringIO()
        code = commands.run_init(
            apply=True,
            bootstrap=False,
            do_git=False,
            start_watch=False,
            run_analyze=False,
            write_docs=False,
            write_hook=False,
            force_docs=False,
            agent_target=agent_target,
            agent_explicit=agent_explicit,
            context=context or make_context(root),
            loaded=loaded(),
            conf_dir=os.path.join(root, "config"),
            stdout=out,
            stderr=io.StringIO(),
            stack=FakeStack(),
        )
        self.assertEqual(code, 0)
        return out.getvalue()

    def _root(self):
        root = tempfile.mkdtemp(prefix="aci-agents-")
        subprocess.run(["git", "init", "-q", root], check=True)
        return project.canon(root)

    def _reread(self, root):
        return project.resolve_project(
            root=root, root_explicit=True, mode="init", workspace=None,
            home=os.path.expanduser("~"), status_all=False,
        )

    def test_apply_records_the_agents_it_applied(self):
        root = self._root()
        out = self._apply(root, "claude")
        self.assertIn("wrote .code-intel (AGENTS=claude)", out)
        self.assertEqual(project.read_code_intel(root).agents, "claude")

    def test_a_second_apply_leaves_the_file_alone(self):
        root = self._root()
        self._apply(root, "claude")
        before = Path(os.path.join(root, ".code-intel")).read_bytes()
        out = self._apply(root, "claude", context=self._reread(root))
        self.assertIn(".code-intel already present (AGENTS=claude)", out)
        self.assertEqual(
            Path(os.path.join(root, ".code-intel")).read_bytes(), before
        )

    def test_applying_a_different_agent_rewrites_the_record(self):
        root = self._root()
        self._apply(root, "claude")
        out = self._apply(
            root, "both", context=self._reread(root), agent_explicit=True
        )
        self.assertIn("updated .code-intel (AGENTS=both, was claude)", out)
        self.assertEqual(project.read_code_intel(root).agents, "both")

    def test_the_recorded_value_drives_a_later_run_without_the_flag(self):
        root = self._root()
        self._apply(root, "claude")
        out = self._apply(root, "both", context=self._reread(root))
        self.assertIn("Agents:    claude (from .code-intel)", out)
        self.assertEqual(project.read_code_intel(root).agents, "claude")

    def test_a_schema_1_project_is_upgraded_by_the_next_apply(self):
        root = self._root()
        with open(os.path.join(root, ".code-intel"), "w") as handle:
            handle.write(
                "SCHEMA=1\nWORKSPACE=demo\nPROJECT=%s\n" % os.path.basename(root)
            )
        out = self._apply(root, "claude", context=self._reread(root))
        self.assertIn("updated .code-intel (AGENTS=claude, was unrecorded)", out)
        self.assertEqual(project.read_code_intel(root).agents, "claude")


if __name__ == "__main__":
    unittest.main()
