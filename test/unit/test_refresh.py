"""The ``refresh`` mode (issue #54): the lighter preflight, the re-index with
its one ``--force`` retry, and the audit that still runs after a failed
re-index. Driven with a fake stack — no real external tool installed.

Ledger: REF-1, REF-3, REF-4, REF-5, REF-7, TOL-2 (``gn_status``), TOL-3, TOL-4,
DEV-8 (header suppressed by ``--json``), FMT-5 (the preflight error block).
"""

import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_code_intel import agent_skills, commands, integrations, project
from agent_code_intel.config import (
    ChildEnvironment,
    CliError,
    LoadedConfig,
    default_config,
)
from agent_code_intel.project import ProjectContext


# --------------------------------------------------------------- fake stack --


class _Stack:
    """Every external call ``refresh`` makes, faked. Defaults model a machine
    with the whole stack healthy and the index already fresh; keyword overrides
    flip individual answers. ``calls`` records argv-ish tuples in order for the
    seam-ordering assertions (issue #54 AC 4)."""

    def __init__(self, **over):
        self._present = set(
            over.get("present", ("grepai", "gitnexus", "git", "ollama", "curl"))
        )
        self._http = over.get("http", True)
        self._grpc = over.get("grpc", True)
        self._ollama_up = over.get("ollama_up", True)
        self._has_model = over.get("has_model", True)
        self._ws_exists = over.get("ws_exists", True)
        self._show = over.get("show", "")
        self._watch = over.get("watch", "watcher running")
        self._gn_status = over.get("gn_status", "index is up-to-date")
        self._analyze = over.get("analyze", integrations.Exec(0, "analyzed 10 files", ""))
        self._force = over.get("force", integrations.Exec(0, "forced", ""))
        self._watch_start = over.get(
            "watch_start", integrations.Exec(0, "watcher started", "")
        )
        self.calls: list[tuple] = []

    # -- generic --
    def have(self, name):
        self.calls.append(("have", name))
        return name in self._present

    def which(self, name):
        return "/usr/bin/%s" % name if name in self._present else ""

    def first_line(self, *argv):
        return "%s 9.9.9" % argv[0]

    # -- preflight probes --
    def qdrant_http_ok(self, url):
        self.calls.append(("qdrant_http", url))
        return self._http

    def qdrant_grpc_ok(self, host, port):
        self.calls.append(("qdrant_grpc", host, port))
        return self._grpc

    def ollama_up(self):
        return self._ollama_up

    def ollama_has_model(self, model):
        return self._has_model

    def gitnexus_runs(self):
        return "gitnexus" in self._present

    # -- audit probes --
    def ws_show(self, ws):
        return self._show

    def ws_exists(self, ws):
        return self._ws_exists

    def watch_status(self, ws):
        self.calls.append(("watch_status", ws))
        return self._watch

    def node_has_register_hooks(self):
        return "node" in self._present

    # -- re-index / watcher --
    def watch_start_background(self, ws):
        self.calls.append(("watch_start_background", ws))
        return self._watch_start

    def gitnexus_analyze_embeddings(self, cwd):
        self.calls.append(("gitnexus_analyze_embeddings", cwd))
        return self._analyze

    def gitnexus_analyze_force(self, cwd):
        self.calls.append(("gitnexus_analyze_force", cwd))
        return self._force

    def gitnexus_status(self, cwd):
        self.calls.append(("gitnexus_status", cwd))
        return self._gn_status


# ------------------------------------------------------------------- helpers --


def _mkrepo(name="proj"):
    root = os.path.join(tempfile.mkdtemp(prefix="aci-refresh-"), name)
    os.makedirs(root)
    subprocess.run(["git", "init", "-q", root], check=True)
    agent_skills.install_targets(root, "both", False)
    return project.canon(root)


def _context(root, workspace="ws"):
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


def _loaded():
    return LoadedConfig(
        config=default_config(),
        child_env=ChildEnvironment({"PATH": ""}),
        config_file="/conf/code-intel/defaults.toml",
        source="defaults",
        conf_paths={},
    )


def _healthy_project(root, workspace="ws"):
    """Write a ``.grepai/config.yaml`` the audit accepts, and return a stack
    override set that maps the workspace here with the configured embedder and a
    running watcher — so the ``--status`` audit inside ``do_refresh`` is clean."""
    cfg = default_config()
    body = "chunking:\n  size: %s\n  overlap: %s\nignore:\n" % (
        cfg.chunk_size,
        cfg.chunk_overlap,
    )
    body += "".join("  - %s\n" % entry for entry in cfg.extra_ignores)
    os.makedirs(os.path.join(root, ".grepai"), exist_ok=True)
    with open(os.path.join(root, ".grepai", "config.yaml"), "w") as handle:
        handle.write(body)
    return {
        "ws_exists": True,
        "show": "  - %s: %s\n  model %s\n" % (os.path.basename(root), root, cfg.embed_model),
        "watch": "watcher running",
    }


def _run(*, stack, context=None, do_grepai=True, do_gitnexus=True, as_json=False):
    context = context or _context(_mkrepo())
    out, err = io.StringIO(), io.StringIO()
    try:
        code = commands.run_refresh(
            as_json=as_json,
            do_grepai=do_grepai,
            do_gitnexus=do_gitnexus,
            agent_target="both",
            context=context,
            loaded=_loaded(),
            stdout=out,
            stderr=err,
            stack=stack,
        )
    except CliError as exc:
        # cli.main owns this translation; reproduce it so a test sees the code.
        err.write("" if not exc.wrap else "[ERROR: %s]\n" % exc)
        code = exc.code
    return code, out.getvalue(), err.getvalue()


# ------------------------------------------------------------------ preflight --


class Preflight(unittest.TestCase):
    def test_nothing_installed_is_exit_1_nothing_refreshed(self):  # REF-4 / FMT-5
        stack = _Stack(present=("curl", "git"), http=False, grpc=False)
        code, out, err = _run(stack=stack)
        self.assertEqual(code, 1)
        self.assertIn("Preflight (--refresh)", out)
        self.assertIn("  MISSING   grepai not on PATH", out)
        self.assertIn("  MISSING   qdrant not healthy at", out)
        self.assertIn("  MISSING   ollama not on PATH", out)
        self.assertIn("  MISSING   gitnexus not on PATH", out)
        self.assertIn("  ok        git on PATH", out)
        # the multi-line block is on stderr, never stdout
        self.assertIn(
            "[ERROR: refresh preflight found 4 unmet dependencies — nothing was refreshed]",
            err,
        )
        self.assertIn("  - grepai not on PATH\n    fix: install GrepAI", err)
        self.assertNotIn("[ERROR:", out)
        # nothing past the preflight ran
        self.assertNotIn("code-intel refresh —", out)
        self.assertNotIn("gitnexus_analyze_embeddings", [c[0] for c in stack.calls])

    def test_one_unmet_is_singular_dependency(self):
        stack = _Stack(present=("grepai", "git", "ollama", "curl"))  # gitnexus gone
        code, _, err = _run(stack=stack)
        self.assertEqual(code, 1)
        self.assertIn("found 1 unmet dependency — nothing was refreshed", err)

    def test_no_grepai_skips_the_grepai_side(self):  # REF-3
        stack = _Stack(present=("git",))  # gitnexus still missing
        code, out, err = _run(stack=stack, do_grepai=False)
        self.assertEqual(code, 1)
        self.assertNotIn("grepai not on PATH", out)
        self.assertNotIn("qdrant", out)
        self.assertIn("  MISSING   gitnexus not on PATH", out)

    def test_no_gitnexus_skips_the_gitnexus_side(self):  # REF-3
        stack = _Stack(present=("curl",), http=False)  # grepai/ollama missing
        code, out, _ = _run(stack=stack, do_gitnexus=False)
        self.assertEqual(code, 1)
        self.assertNotIn("gitnexus not on PATH", out)
        self.assertNotIn("git on PATH", out)
        self.assertIn("  MISSING   grepai not on PATH", out)

    def test_healthy_stack_passes_preflight(self):
        stack = _Stack()
        code, out, _ = _run(stack=stack)
        self.assertIn("  ok        grepai on PATH", out)
        self.assertIn("  ok        qdrant healthy on 6333 (HTTP) and 6334 (gRPC)", out)
        self.assertIn("  ok        ollama responding,", out)
        self.assertNotEqual(code, 1)

    def test_qdrant_http_up_but_grpc_closed(self):
        stack = _Stack(grpc=False)
        _, out, err = _run(stack=stack)
        self.assertIn("gRPC 6334 is closed", out)
        self.assertIn("republish the container with both ports", err)


# ------------------------------------------------------------------- re-index --


class Reindex(unittest.TestCase):
    def test_full_clean_run_is_fresh_exit_0(self):
        root = _mkrepo("widget")
        stack = _Stack(**_healthy_project(root))
        code, out, _ = _run(stack=stack, context=_context(root))
        self.assertEqual(code, 0)
        self.assertIn("already running for workspace ws", out)
        self.assertIn("analyzed 10 files", out)
        self.assertIn("  ok        index up to date", out)
        self.assertIn("Code intelligence is fresh.", out)

    def test_full_analyze_output_is_replayed_without_truncation(self):  # REF-7
        root = _mkrepo("verbose")
        analyze_output = "\n".join("gitnexus line %02d" % i for i in range(25))
        stack = _Stack(
            **_healthy_project(root),
            analyze=integrations.Exec(0, analyze_output, ""),
        )
        code, out, err = _run(stack=stack, context=_context(root))
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertIn("gitnexus line 00", out)
        self.assertIn("gitnexus line 24", out)
        self.assertLess(out.index("gitnexus line 00"), out.index("gitnexus line 24"))

    def test_starts_the_watcher_when_it_is_down(self):
        stack = _Stack(watch="watcher not running")
        _, out, _ = _run(stack=stack)
        self.assertIn("starting watcher for workspace ws...", out)
        self.assertIn("watcher started", out)
        self.assertIn(("watch_start_background", "ws"), stack.calls)

    def test_analyze_persisted_nothing_triggers_the_force_retry(self):  # TOL-4
        stack = _Stack(
            analyze=integrations.Exec(
                1, "", "Embedding generation completed without persisted embeddings"
            ),
            force=integrations.Exec(0, "structural index built", ""),
        )
        code, out, err = _run(stack=stack, do_grepai=False)
        self.assertIn(
            "No GitNexus embeddings were persisted; retrying with structural indexing.",
            out,
        )
        self.assertIn("structural index built", out)
        order = [c[0] for c in stack.calls]
        self.assertLess(
            order.index("gitnexus_analyze_embeddings"),
            order.index("gitnexus_analyze_force"),
        )
        # the force retry succeeded and the index is fresh
        self.assertEqual(code, 0)

    def test_other_analyze_failure_is_not_retried_but_audit_still_runs(self):  # REF-5 / TOL-3
        stack = _Stack(
            analyze=integrations.Exec(2, "", "boom: unrelated crash"),
            gn_status="index is stale",
        )
        code, out, err = _run(stack=stack, do_grepai=False)
        self.assertNotIn("gitnexus_analyze_force", [c[0] for c in stack.calls])
        self.assertIn("boom: unrelated crash", err)
        self.assertIn("gitnexus analyze failed", out)
        # the audit ran despite the failed re-index
        self.assertIn("GitNexus audit", out)
        self.assertIn("index not up to date", out)
        self.assertIn("Code intelligence has drift or errors above.", out)
        self.assertEqual(code, 2)

    def test_stale_index_alone_is_drift_exit_2(self):  # REF-4
        stack = _Stack(gn_status="the index is stale, run analyze")
        code, out, _ = _run(stack=stack, do_grepai=False)
        self.assertEqual(code, 2)
        self.assertIn("  DRIFT     index not up to date", out)

    def test_analyze_runs_in_the_project_root(self):  # AC 4
        root = _mkrepo("rooted")
        stack = _Stack(**_healthy_project(root))
        _run(stack=stack, context=_context(root))
        self.assertIn(("gitnexus_analyze_embeddings", root), stack.calls)
        self.assertIn(("gitnexus_status", root), stack.calls)

    def test_a_force_retry_that_also_fails_still_runs_the_audit(self):  # AC 3 / REF-5
        stack = _Stack(
            analyze=integrations.Exec(
                1, "", "Embedding generation completed without persisted embeddings"
            ),
            force=integrations.Exec(1, "", "still broken"),
            gn_status="index is stale",
        )
        code, out, _ = _run(stack=stack, do_grepai=False)
        order = [c[0] for c in stack.calls]
        self.assertIn("gitnexus_analyze_force", order)
        # the audit ran even though both the embeddings pass and the retry failed
        self.assertLess(order.index("gitnexus_analyze_force"), order.index("gitnexus_status"))
        self.assertIn("gitnexus analyze failed", out)
        self.assertIn("index not up to date", out)
        self.assertEqual(code, 2)


class Ordering(unittest.TestCase):
    """The command sequence through the narrow ``Stack`` seam (issue #54 AC 4):
    left to right it is the reference's (``9406cce`` :1987–:2098)."""

    def test_preflight_probes_the_grepai_side_before_the_gitnexus_side(self):
        stack = _Stack(present=("curl", "git"), http=False)
        _run(stack=stack)
        probes = [c for c in stack.calls if c[0] in ("have", "qdrant_http")]
        grepai_i = probes.index(("have", "grepai"))
        qdrant_i = probes.index(("qdrant_http", "http://127.0.0.1:6333"))
        gitnexus_i = probes.index(("have", "gitnexus"))
        git_i = probes.index(("have", "git"))
        self.assertLess(grepai_i, qdrant_i)
        self.assertLess(qdrant_i, gitnexus_i)
        self.assertLess(gitnexus_i, git_i)

    def test_watcher_start_precedes_the_reindex_which_precedes_the_audit(self):
        stack = _Stack(watch="watcher not running")
        _run(stack=stack, do_gitnexus=True)
        order = [c[0] for c in stack.calls]
        self.assertLess(
            order.index("watch_start_background"),
            order.index("gitnexus_analyze_embeddings"),
        )
        self.assertLess(
            order.index("gitnexus_analyze_embeddings"), order.index("gitnexus_status")
        )


# --------------------------------------------------------------------- shape --


class Shape(unittest.TestCase):
    def test_header_suppressed_by_json(self):  # DEV-8
        stack = _Stack()
        _, plain, _ = _run(stack=stack)
        _, jout, _ = _run(stack=_Stack(), as_json=True)
        self.assertIn("Project:   ", plain)
        self.assertNotIn("Project:   ", jout)

    def test_both_sides_skipped_needs_no_stack(self):
        stack = _Stack(present=())
        code, out, _ = _run(stack=stack, do_grepai=False, do_gitnexus=False)
        self.assertEqual(code, 0)
        self.assertIn("Code intelligence is fresh.", out)
        self.assertEqual(stack.calls, [])

    def test_missing_selected_routing_skill_is_refresh_drift(self):
        root = _mkrepo("routing-drift")
        codex_skill = agent_skills.target_paths(root, "codex")[0][1]
        os.unlink(codex_skill)
        code, out, _ = _run(
            stack=_Stack(present=()),
            context=_context(root),
            do_grepai=False,
            do_gitnexus=False,
        )
        self.assertEqual(code, 2)
        self.assertIn("codex routing skill is missing", out)
        self.assertIn("Code intelligence has drift or errors above.", out)

    def test_only_gitnexus_side_runs_when_grepai_is_off(self):
        stack = _Stack()
        _, out, _ = _run(stack=stack, do_grepai=False)
        self.assertNotIn("GrepAI watcher", out)
        self.assertNotIn("GrepAI audit", out)
        self.assertIn("GitNexus re-index", out)
        self.assertIn("GitNexus audit", out)


if __name__ == "__main__":
    unittest.main()
