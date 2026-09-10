"""The ``remove`` mode (issue #56): planning, ownership guards and ordering."""

import hashlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_code_intel import agent_skills, commands, hooks, project
from agent_code_intel.config import ChildEnvironment, LoadedConfig, default_config
from agent_code_intel.integrations import Exec
from agent_code_intel.project import ProjectContext


def _mkrepo(name="remove-project"):
    root = os.path.join(tempfile.mkdtemp(prefix="aci-remove-"), name)
    os.makedirs(root)
    subprocess.run(["git", "init", "-q", root], check=True)
    return project.canon(root)


def _context(root, workspace="remove-ws"):
    return ProjectContext(
        root=root,
        workspace=workspace,
        proj_name=os.path.basename(root),
        grepai_cfg=os.path.join(root, ".grepai", "config.yaml"),
        mcp_json=os.path.join(root, ".mcp.json"),
        refresh_script=os.path.join(root, "refresh-intel.sh"),
        ident_status="OK",
        ident_workspace=workspace,
        ident_project=os.path.basename(root),
    )


def _loaded(registry):
    return LoadedConfig(
        config=default_config(),
        child_env=ChildEnvironment({"PATH": ""}),
        config_file="/conf/code-intel/defaults.toml",
        source="defaults",
        conf_paths={"REGISTRY": registry},
    )


def _write_pristine_refresh(root, workspace):
    lines = [
        "#!/usr/bin/env bash",
        "# stamp",
        "#",
        'WORKSPACE="%s"' % workspace,
        'PROJECT="whatever"',
        "",
        "echo hi",
    ]
    body = "\n".join(lines)
    stamp = "# code-intel-init: version=9.9.9 body=%s" % hashlib.sha256(
        body.encode()
    ).hexdigest()
    with open(os.path.join(root, "refresh-intel.sh"), "w") as handle:
        handle.write("\n".join([lines[0], stamp] + lines[1:]))


class _Stack:
    def __init__(self, *, mapped=True, remote_code=0):
        self.calls = []
        self.mapped = mapped
        self.remote_code = remote_code

    def watch_status(self, workspace):
        return "watcher running"

    def ws_show(self, workspace):
        if not self.mapped:
            return ""
        return "  - remove-project: %s\n" % self.root

    def codex_mcp_get(self, name):
        self.calls.append(("codex_mcp_get", name))
        return Exec(0, "", "")

    def watch_stop(self, workspace):
        self.calls.append(("watch_stop", workspace))
        return Exec(self.remote_code, "", "")

    def workspace_remove(self, workspace, project_name):
        self.calls.append(("workspace_remove", workspace, project_name))
        return Exec(self.remote_code, "", "")

    def claude_mcp_remove(self, root, name, scope):
        self.calls.append(("claude_mcp_remove", root, name, scope))
        return Exec(self.remote_code, "", "")

    def codex_mcp_remove(self, name):
        self.calls.append(("codex_mcp_remove", name))
        return Exec(self.remote_code, "", "")

    def qdrant_collection_delete(self, http_url, workspace):
        self.calls.append(("qdrant_collection_delete", http_url, workspace))
        return Exec(self.remote_code, "", "")


def _seed_project(root, workspace="remove-ws"):
    with open(os.path.join(root, ".code-intel"), "w") as handle:
        handle.write(
            "SCHEMA=1\nWORKSPACE=%s\nPROJECT=%s\n"
            % (workspace, os.path.basename(root))
        )
    os.makedirs(os.path.join(root, ".grepai"))
    os.makedirs(os.path.join(root, ".gitnexus"))
    with open(os.path.join(root, ".grepai", "config.yaml"), "w") as handle:
        handle.write("owned\n")
    with open(os.path.join(root, ".mcp.json"), "w") as handle:
        handle.write('{"mcpServers":{"grepai":{"args":["--workspace","%s"]}}}' % workspace)
    agent_skills.install_targets(root, "both", False)
    hooks.install(root, "both")


class RemoveMode(unittest.TestCase):
    def test_dry_run_only_plans_and_requires_apply(self):
        root = _mkrepo()
        _seed_project(root)
        _write_pristine_refresh(root, "remove-ws")
        registry = os.path.join(tempfile.mkdtemp(prefix="aci-remove-reg-"), "projects")
        with open(registry, "w") as handle:
            handle.write("remove-ws\t%s\n" % root)
        stack = _Stack()
        stack.root = root
        out, err = io.StringIO(), io.StringIO()

        code = commands.run_remove(
            apply=False,
            as_json=False,
            purge_collection=False,
            agent_target="both",
            context=_context(root),
            loaded=_loaded(registry),
            conf_dir=os.path.dirname(registry),
            stdout=out,
            stderr=err,
            stack=stack,
        )

        self.assertEqual(code, 2)
        self.assertEqual(err.getvalue(), "")
        self.assertIn("rm .code-intel", out.getvalue())
        self.assertIn("rm refresh-intel.sh", out.getvalue())
        self.assertIn("Nothing was changed", out.getvalue())
        self.assertTrue(os.path.exists(os.path.join(root, ".code-intel")))
        self.assertTrue(os.path.exists(os.path.join(root, "refresh-intel.sh")))
        self.assertEqual(stack.calls, [("codex_mcp_get", "grepai-remove-ws")])

    def test_apply_keeps_order_and_deletes_only_owned_content(self):
        root = _mkrepo()
        _seed_project(root)
        _write_pristine_refresh(root, "remove-ws")
        with open(os.path.join(root, "CLAUDE.md"), "w") as handle:
            handle.write("before\n\n<!-- code-intel:start -->owned<!-- code-intel:end -->\nafter\n")
        with open(os.path.join(root, "AGENTS.md"), "w") as handle:
            handle.write("<!-- code-intel:start -->owned<!-- code-intel:end -->\n")
        registry = os.path.join(tempfile.mkdtemp(prefix="aci-remove-reg-"), "projects")
        with open(registry, "w") as handle:
            handle.write("remove-ws\t%s\nother\t/keep\n" % root)
        stack = _Stack()
        stack.root = root
        out, err = io.StringIO(), io.StringIO()

        code = commands.run_remove(
            apply=True,
            as_json=False,
            purge_collection=True,
            agent_target="both",
            context=_context(root),
            loaded=_loaded(registry),
            conf_dir=os.path.dirname(registry),
            stdout=out,
            stderr=err,
            stack=stack,
        )

        self.assertEqual((code, err.getvalue()), (0, ""))
        names = [call[0] for call in stack.calls]
        self.assertEqual(
            names,
            [
                "watch_stop",
                "workspace_remove",
                "claude_mcp_remove",
                "codex_mcp_get",
                "codex_mcp_remove",
                "qdrant_collection_delete",
            ],
        )
        self.assertFalse(os.path.exists(os.path.join(root, ".code-intel")))
        self.assertFalse(os.path.exists(os.path.join(root, ".grepai")))
        self.assertFalse(os.path.exists(os.path.join(root, ".gitnexus")))
        self.assertFalse(os.path.exists(os.path.join(root, "refresh-intel.sh")))
        self.assertFalse(
            os.path.exists(
                os.path.join(
                    root,
                    ".claude",
                    "skills",
                    "agent-code-intel-routing",
                    "SKILL.md",
                )
            )
        )
        self.assertFalse(os.path.exists(os.path.join(root, ".claude")))
        self.assertFalse(
            os.path.exists(
                os.path.join(
                    root,
                    ".agents",
                    "skills",
                    "agent-code-intel-routing",
                    "SKILL.md",
                )
            )
        )
        self.assertEqual(Path(os.path.join(root, "CLAUDE.md")).read_text(), "before\nafter\n")
        self.assertFalse(os.path.exists(os.path.join(root, "AGENTS.md")))
        self.assertEqual(project.read_registry(registry), [("other", "/keep")])
        self.assertIn("left in place", out.getvalue())

    def test_remote_failures_are_tolerated_and_purge_is_optional(self):
        root = _mkrepo()
        _seed_project(root)
        registry = os.path.join(tempfile.mkdtemp(prefix="aci-remove-reg-"), "projects")
        with open(registry, "w") as handle:
            handle.write("remove-ws\t%s\n" % root)
        stack = _Stack(remote_code=1)
        stack.root = root
        out, err = io.StringIO(), io.StringIO()

        code = commands.run_remove(
            apply=True,
            as_json=False,
            purge_collection=False,
            agent_target="both",
            context=_context(root),
            loaded=_loaded(registry),
            conf_dir=os.path.dirname(registry),
            stdout=out,
            stderr=err,
            stack=stack,
        )

        self.assertEqual((code, err.getvalue()), (0, ""))
        self.assertNotIn("qdrant_collection_delete", [call[0] for call in stack.calls])
        self.assertNotIn("DELETE qdrant collection", out.getvalue())

    def test_foreign_code_intel_directory_is_not_removed(self):
        root = _mkrepo()
        foreign = os.path.join(root, ".code-intel")
        os.makedirs(foreign)
        with open(os.path.join(foreign, "keep-me"), "w") as handle:
            handle.write("foreign\n")
        registry = os.path.join(tempfile.mkdtemp(prefix="aci-remove-reg-"), "projects")
        stack = _Stack(mapped=False)
        stack.root = root
        out, err = io.StringIO(), io.StringIO()

        code = commands.run_remove(
            apply=True,
            as_json=False,
            purge_collection=False,
            agent_target="both",
            context=_context(root),
            loaded=_loaded(registry),
            conf_dir=os.path.dirname(registry),
            stdout=out,
            stderr=err,
            stack=stack,
        )

        self.assertEqual((code, err.getvalue()), (0, ""))
        self.assertTrue(os.path.isdir(foreign))
        self.assertEqual(Path(os.path.join(foreign, "keep-me")).read_text(), "foreign\n")

    def test_orphaned_document_markers_are_left_untouched(self):
        root = _mkrepo()
        with open(os.path.join(root, "CLAUDE.md"), "w") as handle:
            handle.write("user\n<!-- code-intel:start -->\n")
        registry = os.path.join(tempfile.mkdtemp(prefix="aci-remove-reg-"), "projects")
        stack = _Stack(mapped=False)
        stack.root = root
        out, err = io.StringIO(), io.StringIO()

        code = commands.run_remove(
            apply=True,
            as_json=False,
            purge_collection=False,
            agent_target="both",
            context=_context(root),
            loaded=_loaded(registry),
            conf_dir=os.path.dirname(registry),
            stdout=out,
            stderr=err,
            stack=stack,
        )

        self.assertEqual(code, 0)
        self.assertEqual(Path(os.path.join(root, "CLAUDE.md")).read_text(), "user\n<!-- code-intel:start -->\n")


if __name__ == "__main__":
    unittest.main()
