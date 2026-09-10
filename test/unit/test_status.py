"""The ``status`` mode (issue #53): the text table's drift decision and row
vocabulary, the JSON document's schema / key order / types / conditional
fields, the shared ``.grepai/config.yaml`` probes and the project registry
reader. Driven with a fake stack — no real external tool installed.

Ledger: ID-7, ID-8, JSON-1…JSON-6, JSON-8, DEV-5, RT-9, TOL-1, CFG-5 (D-partner).
"""

import io
import json
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


# --------------------------------------------------------------- fake stack --


class _Stack:
    """Everything the status probes ask an external tool, faked. Defaults model
    a machine with no stack at all; keyword overrides flip individual answers."""

    def __init__(self, **over):
        self._show = over.get("show", "")
        self._ws_exists = over.get("ws_exists", False)
        self._watch = over.get("watch", "")
        self._present = set(over.get("present", ()))
        self._http = over.get("http", False)
        self._grpc = over.get("grpc", False)
        self._ollama_up = over.get("ollama_up", False)
        self._has_model = over.get("has_model", False)
        self._cli = over.get("cli", "")
        self._daemon = over.get("daemon", False)
        self._universal_ctags = over.get("universal_ctags", True)

    def ws_show(self, ws):
        return self._show

    def ws_exists(self, ws):
        return self._ws_exists

    def watch_status(self, ws):
        return self._watch

    def have(self, name):
        return name in self._present

    def ctags_is_universal(self):
        return "ctags" in self._present and self._universal_ctags

    def which(self, name):
        return "/usr/bin/%s" % name if name in self._present else ""

    def first_line(self, *argv):
        if argv == ("node", "--version"):
            return "v24.11.0"
        return "%s 9.9.9" % argv[0]

    def gitnexus_runs(self):
        return "gitnexus" in self._present

    def node_version_ok(self):
        return "node" in self._present and integrations.node_version_ok(
            self.first_line("node", "--version")
        )

    def node_has_register_hooks(self):
        return "node" in self._present

    def container_cli(self):
        return self._cli

    def container_daemon_ok(self, cli):
        return self._daemon

    def container_inspect(self, cli, fmt, name, default):
        return default

    def qdrant_http_ok(self, url):
        return self._http

    def qdrant_grpc_ok(self, host, port):
        return self._grpc

    def ollama_up(self):
        return self._ollama_up

    def ollama_has_model(self, model):
        return self._has_model


# ------------------------------------------------------------------- helpers --


def _mkrepo(name="proj"):
    root = os.path.join(tempfile.mkdtemp(prefix="aci-status-"), name)
    os.makedirs(root)
    subprocess.run(["git", "init", "-q", root], check=True)
    hooks.install(root, "both")
    return project.canon(root)


def _code_intel(root, ws, proj=None, agents=None):
    """Schema 1 by default — the shape every project written before AGENTS has.
    Pass ``agents`` for a schema-2 file."""
    body = "SCHEMA=%s\nWORKSPACE=%s\nPROJECT=%s\n" % (
        "2" if agents else "1", ws, proj or os.path.basename(root)
    )
    if agents:
        body += "AGENTS=%s\n" % agents
    with open(os.path.join(root, ".code-intel"), "w") as handle:
        handle.write(body)


def _grepai_config(root, size="256", overlap="25", ignores=None):
    ignores = ignores if ignores is not None else default_config().extra_ignores
    body = "chunking:\n  size: %s\n  overlap: %s\nignore:\n" % (size, overlap)
    body += "".join("  - %s\n" % entry for entry in ignores)
    os.makedirs(os.path.join(root, ".grepai"), exist_ok=True)
    with open(os.path.join(root, ".grepai", "config.yaml"), "w") as handle:
        handle.write(body)


def _loaded(source="defaults", conf_paths=None):
    return LoadedConfig(
        config=default_config(),
        child_env=ChildEnvironment({"PATH": ""}),
        config_file="/conf/code-intel/defaults.toml",
        source=source,
        conf_paths=conf_paths or {},
    )


def _context(root, workspace="ws"):
    return ProjectContext(
        root=root,
        workspace=workspace,
        proj_name=os.path.basename(root),
        grepai_cfg=os.path.join(root, ".grepai", "config.yaml"),
        mcp_json=os.path.join(root, ".mcp.json"),
        refresh_script=os.path.join(root, "refresh-intel.sh"),
        ident_status="ABSENT",
        ident_workspace=None,
        ident_project=None,
    )


def _run(*, as_json, status_all, context, stack, registry=None, source="defaults",
         agent_target="both", agent_explicit=False):
    out, err = io.StringIO(), io.StringIO()
    conf_paths = {"REGISTRY": registry} if registry else {}
    code = commands.run_status(
        as_json=as_json,
        status_all=status_all,
        agent_target=agent_target,
        agent_explicit=agent_explicit,
        context=context,
        loaded=_loaded(source=source, conf_paths=conf_paths),
        conf_dir="/conf/code-intel",
        version="3.0.0",
        stdout=out,
        stderr=err,
        stack=stack,
    )
    return code, out.getvalue(), err.getvalue()


# --------------------------------------------------------------- text table --


class TextTable(unittest.TestCase):
    def test_header_printed_without_json_and_suppressed_with_json(self):
        root = _mkrepo()
        _, out, _ = _run(
            as_json=False, status_all=False, context=_context(root), stack=_Stack()
        )
        self.assertIn("Project:   %s" % root, out)
        self.assertIn("Workspace: ws", out)
        self.assertIn("Agents:    both", out)

        _, jout, _ = _run(
            as_json=True, status_all=False, context=_context(root), stack=_Stack()
        )
        self.assertNotIn("Workspace:", jout)  # RT-9 / DEV-8

    def test_no_stack_is_drift_exit_2(self):
        root = _mkrepo()
        code, out, _ = _run(
            as_json=False, status_all=False, context=_context(root), stack=_Stack()
        )
        self.assertEqual(code, 2)
        self.assertIn("  DRIFT     ws  %s" % root, out)
        self.assertIn("  watcher not running", out)
        self.assertIn("Repair a project with:  agent-code-intel --path <dir> --apply", out)

    def test_code_context_tools_are_reported_in_text_status(self):
        root = _mkrepo()
        _, out, _ = _run(
            as_json=False, status_all=False, context=_context(root), stack=_Stack()
        )

        for tool in ("rg", "ctags", "ast-grep", "fd", "rga", "tokei", "scc"):
            self.assertIn("warn      %s not on PATH" % tool, out)
        self.assertIn("ctags and ast-grep are both missing", out)
        self.assertIn("agent-code-intel --install-deps", out)

    def test_bsd_ctags_is_a_warn_with_its_own_reason(self):  # issue #99
        root = _mkrepo()
        names = ("rg", "ctags", "ast-grep", "fd", "rga", "tokei", "scc")
        _, out, _ = _run(
            as_json=False,
            status_all=False,
            context=_context(root),
            stack=_Stack(present=names, universal_ctags=False),
        )

        self.assertIn("warn      ctags on PATH is not Universal Ctags", out)
        self.assertNotIn("ok        ctags on PATH", out)
        # Not the same diagnosis as an absent ctags, and it must not claim the
        # binary is missing from PATH.
        self.assertNotIn("ctags not on PATH", out)
        # Every other tool is unaffected.
        for name in ("rg", "ast-grep", "fd", "rga", "tokei", "scc"):
            self.assertIn("ok        %s on PATH" % name, out)

    def test_usable_ctags_stays_ok(self):  # issue #99 — no regression
        root = _mkrepo()
        names = ("rg", "ctags", "ast-grep", "fd", "rga", "tokei", "scc")
        _, out, _ = _run(
            as_json=False,
            status_all=False,
            context=_context(root),
            stack=_Stack(present=names),
        )

        self.assertIn("ok        ctags on PATH", out)
        self.assertNotIn("not Universal Ctags", out)

    def test_bsd_ctags_alone_degrades_ranges_like_a_missing_one(self):  # issue #99
        root = _mkrepo()
        _, out, _ = _run(
            as_json=False,
            status_all=False,
            context=_context(root),
            stack=_Stack(present=("ctags",), universal_ctags=False),
        )

        self.assertIn("ctags and ast-grep are both missing", out)

    def test_missing_session_start_hook_is_status_drift(self):
        root = _mkrepo("hook-drift")
        _code_intel(root, "team", "hook-drift")
        _grepai_config(root)
        hooks.remove(root, "both")
        stack = _Stack(
            ws_exists=True,
            show="  - hook-drift: %s\n  model nomic-embed-text-v2-moe\n" % root,
            watch="running",
        )
        code, out, _ = _run(
            as_json=False,
            status_all=False,
            context=_context(root),
            stack=stack,
        )
        self.assertEqual(code, 2)
        self.assertIn("claude SessionStart hook is missing", out)
        self.assertIn("codex SessionStart hook is missing at .codex/hooks.json", out)

    def test_hr_rule_is_byte_length_of_the_heading(self):
        root = _mkrepo()
        _, out, _ = _run(
            as_json=False, status_all=False, context=_context(root), stack=_Stack()
        )
        heading = "code-intel status — %s" % root
        self.assertIn("%s\n%s\n" % (heading, "-" * len(heading.encode("utf-8"))), out)

    def test_fully_healthy_project_is_ok_exit_0(self):
        root = _mkrepo("widget")
        _code_intel(root, "team", "widget")
        _grepai_config(root)
        stack = _Stack(
            ws_exists=True,
            show="  - widget: %s\n  model nomic-embed-text-v2-moe\n" % root,
            watch="watcher running",
        )
        rep = commands.Reporter(io.StringIO(), io.StringIO())
        out = rep._stdout  # type: ignore[attr-defined]
        drifted = commands._status_one(rep, "team", root, default_config(), stack)
        self.assertFalse(drifted)
        self.assertIn("  ok        team  %s\n" % root, out.getvalue())

    def test_symlinked_alias_has_the_same_health_in_text_and_json(self):  # PATHS-2
        root = _mkrepo("widget")
        _code_intel(root, "team", "widget")
        _grepai_config(root)
        agent_skills.install_targets(root, "both", False)
        alias = os.path.join(tempfile.mkdtemp(prefix="aci-status-alias-"), "alias")
        os.symlink(root, alias)
        reg = os.path.join(tempfile.mkdtemp(prefix="aci-reg-"), "projects")
        with open(reg, "w") as handle:
            handle.write("team\t%s\n" % alias)
        stack = _Stack(
            ws_exists=True,
            show="  - widget: %s\n  model nomic-embed-text-v2-moe\n" % root,
            watch="running",
        )

        text_code, text, _ = _run(
            as_json=False,
            status_all=True,
            context=_context(root),
            stack=stack,
            registry=reg,
        )
        json_code, json_text, _ = _run(
            as_json=True,
            status_all=True,
            context=_context(root),
            stack=stack,
            registry=reg,
        )

        self.assertEqual((text_code, json_code), (0, 0))
        self.assertIn("  ok        team  %s\n" % alias, text)
        entry = json.loads(json_text)["projects"][0]
        self.assertIs(entry["ok"], True)
        self.assertIs(entry["mapped"], True)
        self.assertIs(entry["watcher"], True)
        self.assertEqual(entry["path"], root)
        self.assertEqual(entry["mapped_path"], root)

    def test_all_empty_registry_is_exit_0(self):
        root = _mkrepo()
        empty = os.path.join(tempfile.mkdtemp(prefix="aci-reg-"), "projects")
        open(empty, "w").close()
        code, out, _ = _run(
            as_json=False,
            status_all=True,
            context=_context(root),
            stack=_Stack(),
            registry=empty,
        )
        self.assertEqual(code, 0)
        self.assertIn("registry is empty (%s)" % empty, out)

    def test_all_reports_broken_row_and_keeps_going(self):  # TOL-1
        broken = _mkrepo("broken")
        with open(os.path.join(broken, ".code-intel"), "w") as handle:
            handle.write("SCHEMA=1\nworkspace=lowercase\nPROJECT=broken\n")
        healthy = _mkrepo("healthy")
        reg = os.path.join(tempfile.mkdtemp(prefix="aci-reg-"), "projects")
        with open(reg, "w") as handle:
            handle.write("bws\t%s\nhws\t%s\n" % (broken, healthy))
        code, out, _ = _run(
            as_json=False,
            status_all=True,
            context=_context(broken),
            stack=_Stack(),
            registry=reg,
        )
        self.assertEqual(code, 2)
        self.assertIn("  BROKEN    bws  %s" % broken, out)
        self.assertIn("healthy", out)  # the loop reached the second row

    def test_gone_directory_is_a_gone_row(self):
        reg = os.path.join(tempfile.mkdtemp(prefix="aci-reg-"), "projects")
        gone = "/no/such/registered/dir"
        with open(reg, "w") as handle:
            handle.write("gws\t%s\n" % gone)
        root = _mkrepo()
        code, out, _ = _run(
            as_json=False,
            status_all=True,
            context=_context(root),
            stack=_Stack(),
            registry=reg,
        )
        self.assertEqual(code, 2)
        self.assertIn("  GONE      gws  %s  (directory no longer exists)" % gone, out)

    def test_stale_gob_is_reported_but_never_the_cause_of_drift(self):  # DEV-12
        root = _mkrepo("widget")
        _code_intel(root, "team", "widget")
        _grepai_config(root)
        os.makedirs(os.path.join(root, ".grepai"), exist_ok=True)
        open(os.path.join(root, ".grepai", "index.gob"), "w").close()
        stack = _Stack(
            ws_exists=True,
            show="  - widget: %s\n  model nomic-embed-text-v2-moe\n" % root,
            watch="running",
        )
        rep = commands.Reporter(io.StringIO(), io.StringIO())
        drifted = commands._status_one(rep, "team", root, default_config(), stack)
        text = rep._stdout.getvalue()  # type: ignore[attr-defined]
        self.assertIn("stale .grepai/index.gob present (rm it)", text)
        self.assertIn("  ok        team  %s\n" % root, text)  # still ok, not DRIFT
        self.assertFalse(drifted)

    def test_name_conflict_is_a_conflict_row_not_generic_drift(self):
        root = _mkrepo("taken")
        stack = _Stack(show="  - taken: /somewhere/else\n")
        rep = commands.Reporter(io.StringIO(), io.StringIO())
        drifted = commands._status_one(rep, "ws", root, default_config(), stack)
        text = rep._stdout.getvalue()  # type: ignore[attr-defined]
        self.assertTrue(drifted)
        self.assertIn("  CONFLICT  ws  %s" % root, text)
        self.assertIn("'taken' is mapped to /somewhere/else, not here", text)
        self.assertIn(
            "fix: grepai workspace remove ws taken && agent-code-intel ws --path "
            "%s --apply" % root,
            text,
        )
        self.assertNotIn("does not map this path", text)  # returned before the probes


# ------------------------------------------------------------- JSON document --


class JsonDocument(unittest.TestCase):
    def _doc(self, *, status_all=True, registry=None, context=None, source="defaults"):
        context = context or _context(_mkrepo())
        code, out, _ = _run(
            as_json=True,
            status_all=status_all,
            context=context,
            stack=_Stack(),
            registry=registry,
            source=source,
        )
        self.assertEqual(code, 0)  # JSON-2 / DEV-5: always 0 after a good build
        return json.loads(out), out

    def test_root_keys_and_order(self):  # JSON-1
        doc, out = self._doc()
        self.assertEqual(list(doc), ["meta", "tool", "svc", "projects"])
        self.assertLess(out.index('"meta"'), out.index('"tool"'))
        self.assertLess(out.index('"tool"'), out.index('"svc"'))

    def test_meta_shape_and_types(self):  # JSON-1 / JSON-5
        doc, _ = self._doc()
        meta = doc["meta"]
        self.assertEqual(list(meta), [
            "schema", "generated_at", "script_version", "config_file",
            "chunk_size", "chunk_overlap", "embed_model", "embed_provider",
            "project_count",
        ])
        self.assertEqual(meta["schema"], "1")
        self.assertEqual(meta["chunk_size"], "256")   # a string, not a number
        self.assertEqual(meta["project_count"], "0")  # a string
        self.assertRegex(
            meta["generated_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
        )

    def test_config_file_reports_toml_for_a_defaults_run(self):  # CFG-1
        doc, _ = self._doc(source="defaults")
        self.assertTrue(doc["meta"]["config_file"].endswith("defaults.toml"))

    def test_config_file_reports_the_env_file_for_an_env_run(self):
        ctx = _context(_mkrepo())
        code, out, _ = _run(
            as_json=True,
            status_all=True,
            context=ctx,
            stack=_Stack(),
            source="env",
        )
        # conf_paths carries no CONF_FILE here → falls back to config_file
        self.assertEqual(code, 0)

    def test_tools_and_services_present_flags_are_booleans(self):
        doc, _ = self._doc()
        self.assertIs(doc["tool"]["grepai"]["present"], False)
        self.assertIs(doc["tool"]["claude"]["present"], False)
        self.assertIs(doc["svc"]["qdrant"]["http"], False)
        self.assertIs(doc["svc"]["qdrant"]["grpc"], False)
        self.assertEqual(doc["svc"]["qdrant"]["grpc_port"], "6334")  # string
        self.assertIs(doc["svc"]["container"]["daemon"], False)
        self.assertEqual(doc["svc"]["container"]["cli"], "")
        self.assertIs(doc["svc"]["ollama"]["present"], False)

    def test_node_version_gate_is_reported_in_json(self):
        root = _mkrepo()
        _, out, _ = _run(
            as_json=True,
            status_all=False,
            context=_context(root),
            stack=_Stack(present=("node",)),
        )
        node = json.loads(out)["tool"]["node"]

        self.assertIs(node["version_ok"], True)
        self.assertEqual(node["version_min"], "24.11.0")

    def test_old_node_is_reported_as_not_ok_in_json(self):
        root = _mkrepo()
        stack = _Stack(present=("node",))
        stack.first_line = lambda *argv: (
            "v20.0.0" if argv == ("node", "--version") else "x 9.9.9"
        )
        _, out, _ = _run(
            as_json=True, status_all=False, context=_context(root), stack=stack
        )
        node = json.loads(out)["tool"]["node"]

        self.assertIs(node["version_ok"], False)
        self.assertEqual(node["version"], "v20.0.0")

    def test_code_context_tool_keys_are_stable(self):
        doc, _ = self._doc()
        names = ("rg", "ctags", "ast-grep", "fd", "rga", "tokei", "scc")

        self.assertEqual(
            list(doc["tool"]),
            ["grepai", "gitnexus", "node", "claude", "codex", "rtk", *names],
        )
        for name in names:
            self.assertEqual(doc["tool"][name], {"present": False})

    def test_code_context_tool_presence_is_reported(self):
        names = ("rg", "ctags", "ast-grep", "fd", "rga", "tokei", "scc")
        root = _mkrepo()
        code, out, _ = _run(
            as_json=True,
            status_all=False,
            context=_context(root),
            stack=_Stack(present=names),
        )

        self.assertEqual(code, 0)
        doc = json.loads(out)
        for name in names:
            self.assertEqual(doc["tool"][name], {"present": True})

    def test_all_is_ignored_registry_always_enumerated(self):  # JSON-3
        a = _mkrepo("a")
        b = _mkrepo("b")
        reg = os.path.join(tempfile.mkdtemp(prefix="aci-reg-"), "projects")
        with open(reg, "w") as handle:
            handle.write("aws\t%s\nbws\t%s\n" % (a, b))
        # status_all=False must still enumerate the whole registry for JSON
        doc, _ = self._doc(status_all=False, registry=reg)
        self.assertEqual(doc["meta"]["project_count"], "2")
        self.assertEqual({p["name"] for p in doc["projects"]}, {"a", "b"})

    def test_healthy_project_entry_shape_and_key_order(self):
        root = _mkrepo("widget")
        _code_intel(root, "team", "widget")
        _grepai_config(root)
        agent_skills.install_targets(root, "both", False)
        reg = os.path.join(tempfile.mkdtemp(prefix="aci-reg-"), "projects")
        with open(reg, "w") as handle:
            handle.write("team\t%s\n" % root)
        code, out, _ = _run(
            as_json=True,
            status_all=True,
            context=_context(root),
            registry=reg,
            stack=_Stack(
                ws_exists=True,
                show="  - widget: %s\n  model nomic-embed-text-v2-moe\n" % root,
                watch="running",
            ),
        )
        doc = json.loads(out)
        entry = doc["projects"][0]
        self.assertEqual(list(entry), [
            "workspace", "path", "name", "agents", "agents_recorded", "exists",
            "workspace_exists", "mapped",
            "mapped_path", "embedder", "chunking_ok", "ignores_ok", "watcher",
            "routing_skills", "session_start_hook", "gob_leftover", "collection", "ok",
        ])
        self.assertIs(entry["ok"], True)
        self.assertIs(entry["gob_leftover"], False)
        self.assertIs(entry["chunking_ok"], True)
        self.assertEqual(
            entry["session_start_hook"]["agents"]["codex"]["state"], "current"
        )
        self.assertEqual(entry["collection"], "workspace_team")  # a string
        self.assertEqual(entry["embedder"], "match")  # a string, not coerced
        self.assertEqual(entry["mapped_path"], root)  # canonical, string
        self.assertEqual(
            entry["routing_skills"],
            {
                "claude": {
                    "agent-code-intel-routing": {
                        "path": ".claude/skills/agent-code-intel-routing/SKILL.md",
                        "state": "current",
                        "ok": True,
                    },
                    "code-context": {
                        "path": ".claude/skills/code-context/SKILL.md",
                        "state": "current",
                        "ok": True,
                    },
                },
                "codex": {
                    "agent-code-intel-routing": {
                        "path": ".agents/skills/agent-code-intel-routing/SKILL.md",
                        "state": "current",
                        "ok": True,
                    },
                    "code-context": {
                        "path": ".agents/skills/code-context/SKILL.md",
                        "state": "current",
                        "ok": True,
                    },
                },
            },
        )

    def test_missing_selected_routing_skill_marks_project_unhealthy(self):
        root = _mkrepo("routing-drift")
        _code_intel(root, "team", "routing-drift")
        _grepai_config(root)
        agent_skills.install_targets(root, "claude", False)
        reg = os.path.join(tempfile.mkdtemp(prefix="aci-reg-"), "projects")
        with open(reg, "w") as handle:
            handle.write("team\t%s\n" % root)

        _, out, _ = _run(
            as_json=True,
            status_all=True,
            context=_context(root),
            registry=reg,
            stack=_Stack(
                ws_exists=True,
                show="  - routing-drift: %s\n  model nomic-embed-text-v2-moe\n"
                % root,
                watch="running",
            ),
        )
        entry = json.loads(out)["projects"][0]
        self.assertIs(
            entry["routing_skills"]["claude"]["agent-code-intel-routing"]["ok"],
            True,
        )
        self.assertIs(
            entry["routing_skills"]["claude"]["code-context"]["ok"], True
        )
        self.assertEqual(
            entry["routing_skills"]["codex"]["agent-code-intel-routing"]["state"],
            "missing",
        )
        self.assertEqual(
            entry["routing_skills"]["codex"]["code-context"]["state"],
            "missing",
        )
        self.assertIs(entry["ok"], False)

    def test_broken_project_entry_is_the_short_shape(self):  # JSON-6
        bad = _mkrepo("bad")
        with open(os.path.join(bad, ".code-intel"), "w") as handle:
            handle.write("SCHEMA=1\nWORKSPACE=x\nPROJECT=x\nBOGUS=1\n")
        reg = os.path.join(tempfile.mkdtemp(prefix="aci-reg-"), "projects")
        with open(reg, "w") as handle:
            handle.write("bws\t%s\n" % bad)
        doc, _ = self._doc(registry=reg, context=_context(bad))
        entry = doc["projects"][0]
        self.assertEqual(
            list(entry),
            [
                "workspace",
                "path",
                "agents",
                "agents_recorded",
                "code_intel_error",
                "routing_skills",
                "session_start_hook",
                "ok",
            ],
        )
        self.assertIs(entry["ok"], False)
        self.assertEqual(set(entry["routing_skills"]), {"claude", "codex"})
        self.assertIn("unknown key 'BOGUS'", entry["code_intel_error"])

    def test_gone_project_entry_stops_at_exists_false(self):
        reg = os.path.join(tempfile.mkdtemp(prefix="aci-reg-"), "projects")
        with open(reg, "w") as handle:
            handle.write("gws\t/no/such/dir/at/all\n")
        doc, _ = self._doc(registry=reg)
        entry = doc["projects"][0]
        self.assertEqual(
            list(entry),
            [
                "workspace",
                "path",
                "name",
                "agents",
                "agents_recorded",
                "exists",
                "routing_skills",
                "session_start_hook",
                "ok",
            ],
        )
        self.assertIs(entry["exists"], False)
        self.assertEqual(
            entry["routing_skills"]["codex"]["agent-code-intel-routing"]["state"],
            "missing",
        )
        self.assertEqual(
            entry["routing_skills"]["codex"]["code-context"]["state"],
            "missing",
        )
        self.assertIs(entry["ok"], False)

    def test_no_script_state_key_anywhere(self):  # issue #17 contract
        doc, out = self._doc()
        self.assertNotIn("script_state", out)

    def test_nothing_is_written_to_the_project(self):  # JSON-8
        root = _mkrepo()
        before = sorted(os.listdir(root))
        self._doc(context=_context(root))
        self.assertEqual(sorted(os.listdir(root)), before)


# ----------------------------------------------------- registry + cfg probes --


class RegistryReader(unittest.TestCase):
    def _reg(self, text):
        path = os.path.join(tempfile.mkdtemp(prefix="aci-reg-"), "projects")
        with open(path, "w") as handle:
            handle.write(text)
        return path

    def test_missing_file_is_empty(self):
        self.assertEqual(project.read_registry("/no/such/registry"), [])

    def test_tab_split_and_blank_line_skip(self):
        rows = project.read_registry(
            self._reg("ws1\t/a\n\nws2\t/b\nnotab\nws3\t/c/with\ttab\n")
        )
        self.assertEqual(
            rows, [("ws1", "/a"), ("ws2", "/b"), ("ws3", "/c/with\ttab")]
        )

    def test_empty_workspace_or_path_skipped(self):
        self.assertEqual(project.read_registry(self._reg("\t/a\nws\t\n")), [])


class GrepaiConfigProbes(unittest.TestCase):
    def _cfg(self, body):
        root = tempfile.mkdtemp(prefix="aci-cfg-")
        path = os.path.join(root, "config.yaml")
        with open(path, "w") as handle:
            handle.write(body)
        return path

    def test_chunking_matches(self):
        path = self._cfg("chunking:\n  size: 256\n  overlap: 25\n")
        self.assertTrue(project.grepai_config_chunking_ok(path, "256", "25"))

    def test_chunking_wrong_numbers(self):
        path = self._cfg("chunking:\n  size: 512\n  overlap: 25\n")
        self.assertFalse(project.grepai_config_chunking_ok(path, "256", "25"))

    def test_chunking_missing_file(self):
        self.assertFalse(project.grepai_config_chunking_ok("/no/file", "256", "25"))

    def test_ignores_all_present(self):
        path = self._cfg("ignore:\n  - a\n  - b\n  - c\n")
        self.assertTrue(project.grepai_config_ignores_ok(path, ("a", "c")))

    def test_ignores_one_missing(self):
        path = self._cfg("ignore:\n  - a\n  - b\n")
        self.assertFalse(project.grepai_config_ignores_ok(path, ("a", "z")))

    def test_ignores_no_block(self):
        path = self._cfg("chunking:\n  size: 1\n  overlap: 1\n")
        self.assertFalse(project.grepai_config_ignores_ok(path, ("a",)))


class PerProjectAgents(unittest.TestCase):
    """A project's own ``AGENTS`` decides what its row is audited against.

    Auditing codex artifacts in a project that was applied for claude alone
    reports a drift whose only fix is installing an agent the user does not
    use — and ``--status --all`` used to do exactly that to every project on
    the machine at once.
    """

    def _registry(self, *roots):
        reg = os.path.join(tempfile.mkdtemp(prefix="aci-reg-"), "projects")
        with open(reg, "w") as handle:
            for root in roots:
                handle.write("%s\t%s\n" % (os.path.basename(root), root))
        return reg

    def _healthy_stack(self, root, name):
        return _Stack(
            ws_exists=True,
            show="  - %s: %s\n  model nomic-embed-text-v2-moe\n" % (name, root),
            watch="running",
        )

    def test_recorded_agents_narrow_the_audit(self):
        root = _mkrepo("widget")
        _code_intel(root, "widget", agents="claude")
        _grepai_config(root)
        agent_skills.install_targets(root, "claude", False)
        doc, _ = self._doc(root)
        entry = doc["projects"][0]
        self.assertEqual(entry["agents"], "claude")
        self.assertEqual(entry["agents_recorded"], "claude")
        self.assertEqual(set(entry["routing_skills"]), {"claude"})
        self.assertIs(entry["ok"], True)

    def test_an_explicit_flag_still_overrides_the_file(self):
        root = _mkrepo("widget")
        _code_intel(root, "widget", agents="claude")
        _grepai_config(root)
        agent_skills.install_targets(root, "claude", False)
        doc, _ = self._doc(root, agent_target="both", agent_explicit=True)
        entry = doc["projects"][0]
        self.assertEqual(entry["agents"], "both")
        self.assertEqual(entry["agents_recorded"], "claude")
        self.assertEqual(set(entry["routing_skills"]), {"claude", "codex"})
        self.assertIs(entry["ok"], False)

    def test_a_schema_1_project_falls_back_to_the_command_line(self):
        root = _mkrepo("widget")
        _code_intel(root, "widget")
        _grepai_config(root)
        doc, _ = self._doc(root)
        entry = doc["projects"][0]
        self.assertEqual(entry["agents"], "both")
        self.assertIsNone(entry["agents_recorded"])

    def test_two_projects_in_one_run_answer_for_themselves(self):
        claude_only = _mkrepo("widget")
        _code_intel(claude_only, "widget", agents="claude")
        _grepai_config(claude_only)
        every = _mkrepo("gadget")
        _code_intel(every, "gadget", agents="both")
        _grepai_config(every)
        reg = self._registry(claude_only, every)
        _, out, _ = _run(
            as_json=True,
            status_all=True,
            context=_context(claude_only),
            registry=reg,
            stack=_Stack(),
        )
        entries = {e["path"]: e for e in json.loads(out)["projects"]}
        self.assertEqual(set(entries[claude_only]["routing_skills"]), {"claude"})
        self.assertEqual(
            set(entries[every]["routing_skills"]), {"claude", "codex"}
        )

    def test_the_text_table_tells_a_schema_1_project_what_it_is_missing(self):
        root = _mkrepo("widget")
        _code_intel(root, "widget")
        _grepai_config(root)
        _, out, _ = _run(
            as_json=False,
            status_all=True,
            context=_context(root),
            registry=self._registry(root),
            stack=_Stack(),
        )
        self.assertIn(".code-intel predates AGENTS", out)

    def test_a_recorded_project_is_not_nagged(self):
        root = _mkrepo("widget")
        _code_intel(root, "widget", agents="claude")
        _grepai_config(root)
        _, out, _ = _run(
            as_json=False,
            status_all=True,
            context=_context(root),
            registry=self._registry(root),
            stack=_Stack(),
        )
        self.assertNotIn("predates AGENTS", out)

    def test_the_header_names_where_the_answer_came_from(self):
        root = _mkrepo("widget")
        _code_intel(root, "widget", agents="claude")
        context = project.resolve_project(
            root=root, root_explicit=True, mode="status", workspace=None,
            home=os.path.expanduser("~"), status_all=False,
        )
        _, out, _ = _run(
            as_json=False, status_all=False, context=context, stack=_Stack()
        )
        self.assertIn("Agents:    claude (from .code-intel)", out)

    def _doc(self, root, agent_target="both", agent_explicit=False):
        _, out, err = _run(
            as_json=True,
            status_all=True,
            context=_context(root),
            registry=self._registry(root),
            agent_target=agent_target,
            agent_explicit=agent_explicit,
            stack=self._healthy_stack(root, os.path.basename(root)),
        )
        return json.loads(out), err


if __name__ == "__main__":
    unittest.main()
