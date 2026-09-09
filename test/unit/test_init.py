"""Preview/apply orchestration for issue #55."""

import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_code_intel import commands, integrations, project
from agent_code_intel.config import ChildEnvironment, LoadedConfig, default_config
from agent_code_intel.project import ProjectContext


class FakeStack:
    def __init__(self, present=()):
        self.present = set(present or ("grepai", "gitnexus", "curl", "git", "claude", "codex", "ollama"))
        self.calls = []
        self.workspace = False

    def have(self, name):
        self.calls.append(("have", name))
        return name in self.present

    def first_line(self, *argv):
        return "gitnexus 9.9.9"

    def gitnexus_runs(self):
        return True

    def node_has_register_hooks(self):
        return True

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


if __name__ == "__main__":
    unittest.main()
