"""code-intel-dash — the only things it writes, and the gates in front of it.

Pausing a project, remembering that pause, retiring a project and bringing it
back, the verdicts built on top of them, and the gates in front of every
request. The dashboard is a script, not a module, so it is loaded from its path.
GrepAI is a fake watcher held in memory, HOME and XDG_CONFIG_HOME are throwaway
trees, and the HTTP gates are tested against a real server on an ephemeral
loopback port.

No stack, no network beyond 127.0.0.1 — every class patches the subprocess
runner and the config location, so nothing here can reach a real registry or a
real watcher.
"""

import importlib.machinery
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from agent_code_intel import cli, commands, config, integrations, project


def _load_dash():
    loader = importlib.machinery.SourceFileLoader("code_intel_dash", str(REPO / "code-intel-dash"))
    spec = importlib.util.spec_from_loader("code_intel_dash", loader)
    module = importlib.util.module_from_spec(spec)
    saved, sys.dont_write_bytecode = sys.dont_write_bytecode, True   # no .pyc beside the script
    try:
        loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = saved
    return module


dash = _load_dash()


class FakeGrepai:
    """`grepai` for a handful of workspaces, in memory.

    ``watch --background`` exits 1 after "waiting" even though the watcher came
    up — the real grepai does exactly that, and the dashboard must not believe
    it. Anything else it is asked is recorded and answered with an error.
    """

    def __init__(self):
        self.alive = {}
        self.stuck = set()               # workspaces whose watcher ignores --stop
        self.calls = []
        self.lock = threading.Lock()

    def log(self, ws, line):
        p = dash.log_path(ws)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a") as f:
            f.write("[grepai-workspace-%s] %s\n" % (ws, line))

    def __call__(self, cmd, timeout=25):
        with self.lock:
            self.calls.append(list(cmd))
        if cmd[:2] != ["grepai", "watch"]:
            return 1, "", "fake grepai: %s" % " ".join(cmd[1:3])
        ws, flag = cmd[3], cmd[4]
        if flag == "--status":
            return 0, ("Watcher is running" if self.alive.get(ws) else "Watcher is not running"), ""
        if flag == "--stop":
            if ws in self.stuck:
                return 1, "", "failed to stop watcher"
            self.log(ws, "Shutting down...")
            self.alive[ws] = False
            return 0, "Watcher stopped", ""
        if flag == "--background":
            self.alive[ws] = True
            self.log(ws, "Watching 1 projects for changes...")
            return 1, "", "timeout waiting for process to become ready"
        return 2, "", "unexpected flag %s" % flag


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aci-dash-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(self.home)

        # agent-code-intel's config directory is ${XDG_CONFIG_HOME}/code-intel;
        # with no defaults file in it, the registry is <conf>/projects.
        env = mock.patch.dict(os.environ, {"HOME": self.home,
                                           "XDG_CONFIG_HOME": os.path.join(self.tmp, "xdg")})
        env.start()
        self.addCleanup(env.stop)
        self.conf = cli._conf_dir(os.environ)

        # The repository's own package, never whatever is installed on PATH.
        saved_pkg = dict(dash._pkg)
        dash._pkg.clear()
        dash._pkg.update(project=project, config=config, integrations=integrations,
                         cli=cli, commands=commands, err=None)
        self.addCleanup(lambda: (dash._pkg.clear(), dash._pkg.update(saved_pkg)))

        saved_doc = dash._last_status["doc"]
        self.addCleanup(dash._last_status.__setitem__, "doc", saved_doc)

        self.grepai = FakeGrepai()
        run = mock.patch.object(dash, "run", self.grepai)
        run.start()
        self.addCleanup(run.stop)

        self.registry, self.retired, err = dash.registry_paths()
        self.assertIsNone(err)
        for p in (self.registry, self.retired, dash.paused_file(), dash.log_path("x")):
            self.assertTrue(p.startswith(self.tmp), "%s escapes the temp tree" % p)

    def make_project(self, ws, running=True, identity_ws=None):
        path = os.path.join(self.tmp, "src", ws)
        for d in (".grepai", ".gitnexus"):
            os.makedirs(os.path.join(path, d))
        if identity_ws:
            with open(os.path.join(path, ".code-intel"), "w") as f:
                f.write("SCHEMA=2\nWORKSPACE=%s\nPROJECT=%s\nAGENTS=claude\n" % (identity_ws, ws))
        project.registry_add(self.registry, ws, path)
        self.grepai.alive[identity_ws or ws] = running
        return path


# ------------------------------------------------------------------ pause ---

class PauseTest(Base):
    def test_pause_is_recorded_and_resume_forgets_it(self):
        self.make_project("alpha")
        r = dash.watcher_set("alpha", "stop")
        self.assertEqual(r, {"ok": True, "message": "watcher stopped"})
        self.assertIn("alpha", dash.read_paused())

        r = dash.watcher_set("alpha", "start")
        self.assertEqual(r, {"ok": True, "message": "watcher started"})
        self.assertNotIn("alpha", dash.read_paused())

    def test_start_verdict_is_the_watcher_not_the_exit_code(self):
        self.make_project("alpha", running=False)
        r = dash.watcher_set("alpha", "start")          # grepai exits 1, watcher is up
        self.assertTrue(r["ok"], r)

    def test_stop_that_leaves_the_watcher_running_fails_and_records_nothing(self):
        self.make_project("alpha")
        self.grepai.stuck.add("alpha")
        r = dash.watcher_set("alpha", "stop")
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], "failed to stop watcher")
        self.assertEqual(dash.read_paused(), {})

    def test_malformed_workspace_is_refused_before_anything_runs(self):
        for ws in ("", "../etc", "-rf", "a b", "x" * 200):
            self.assertFalse(dash.watcher_set(ws, "stop")["ok"], ws)
        self.assertEqual(self.grepai.calls, [])

    def test_without_the_package_nothing_is_paused_or_resumed(self):
        self.make_project("alpha")
        dash._pkg.clear()
        dash._pkg.update(err="the agent_code_intel package was not found")
        r = dash.watcher_set("alpha", "stop")
        self.assertEqual(r, {"ok": False, "error": "the agent_code_intel package was not found"})
        self.assertEqual(self.grepai.calls, [])

    def test_two_pauses_at_once_are_both_kept(self):
        names = ("alpha", "beta", "gamma", "delta")
        for ws in names:
            self.make_project(ws)
        threads = [threading.Thread(target=dash.remember_pause, args=(ws, True)) for ws in names]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(dash.read_paused()), sorted(names))

    def test_an_unreadable_note_is_no_pauses_and_is_rewritten(self):
        os.makedirs(self.conf, exist_ok=True)
        with open(dash.paused_file(), "w") as f:
            f.write("{not json")
        self.assertEqual(dash.read_paused(), {})
        self.assertIsNone(dash.remember_pause("alpha", True))
        self.assertEqual(list(dash.read_paused()), ["alpha"])

    def test_a_pause_holds_until_the_watcher_logs_again(self):
        self.make_project("alpha")
        dash.watcher_set("alpha", "stop")
        since = dash.read_paused()["alpha"]
        self.assertTrue(dash.pause_holds("alpha", since))

        # Something started it since — --refresh, --apply, by hand.
        later = since + dash.PAUSE_GRACE_S + 60
        os.utime(dash.log_path("alpha"), (later, later))
        self.assertFalse(dash.pause_holds("alpha", since))

    def test_no_note_is_no_pause_and_no_log_is_a_pause_that_holds(self):
        self.assertFalse(dash.pause_holds("alpha", None))
        self.assertTrue(dash.pause_holds("never-logged", time.time()))


class VerdictTest(unittest.TestCase):
    def test_a_pause_is_not_config_drift_but_anything_else_is(self):
        # agent-code-intel's own `ok` is false for every stopped watcher, and
        # `drift` names what failed.
        watcher_only = {"ok": False, "drift": ["watcher"]}
        self.assertTrue(dash.config_ok(watcher_only, paused=True))
        self.assertFalse(dash.config_ok(watcher_only, paused=False))     # stopped, not by us
        self.assertFalse(dash.config_ok({"ok": False, "drift": ["watcher", "mapping"]}, paused=True))
        self.assertFalse(dash.config_ok({"ok": False, "drift": ["exists"]}, paused=True))
        self.assertTrue(dash.config_ok({"ok": True, "drift": []}, paused=False))

    def test_a_report_without_the_drift_list_gets_no_leniency(self):
        self.assertFalse(dash.config_ok({"ok": False}, paused=True))

    def test_once_does_not_fail_on_a_pause(self):
        paused = {"status_error": None, "components": {"qdrant": {"ok": True}},
                  "projects": [{"ok": False, "paused": True, "config_ok": True,
                                "gitnexus": {"ok": True}}]}
        self.assertFalse(dash.report_is_bad(paused))
        crashed = dict(paused, projects=[dict(paused["projects"][0], paused=False, config_ok=False)])
        self.assertTrue(dash.report_is_bad(crashed))
        self.assertTrue(dash.report_is_bad(dict(paused, components={"qdrant": {"ok": False}})))
        self.assertTrue(dash.report_is_bad({"status_error": "boom"}))


class DriftContractTest(unittest.TestCase):
    """The drift list the dashboard reads is agent-code-intel's own: a stopped
    watcher on an otherwise healthy project is exactly ["watcher"]."""

    def test_the_real_status_names_a_stopped_watcher_alone(self):
        import test_status as ts

        entry = ts.DriftNames("test_a_stopped_watcher_is_named_alone")._entry(watch="")
        self.assertIs(entry["ok"], False)
        self.assertTrue(dash.config_ok(entry, paused=True))
        drifted = ts.DriftNames("test_a_stopped_watcher_is_named_alone")._entry(
            watch="", mapped_to="/elsewhere")
        self.assertFalse(dash.config_ok(drifted, paused=True))


class ReportTest(Base):
    """build_report() with every probe stubbed: only `paused` and `config_ok` are real."""

    def report(self, projects):
        status = {"meta": {}, "svc": {}, "projects": projects}
        stubs = {
            "find_script": lambda: "/nonexistent/agent-code-intel",
            "check_status": lambda script: (status, None),
            "check_qdrant": lambda *a: {"ok": False, "collections": []},
            "check_mcp_servers": lambda: {"ok": True, "servers": []},
            "check_gitnexus": lambda path: {"ok": True},
            "check_watcher_log": lambda ws: {"ok": True},
        }
        with mock.patch.multiple(dash, **stubs):
            return {p["workspace"]: p for p in dash.build_report()["projects"]}

    def row(self, ws, path, watcher):
        drift = [] if watcher else ["watcher"]
        return {"workspace": ws, "path": path, "watcher": watcher, "exists": True,
                "ok": not drift, "drift": drift}

    def test_paused_only_while_the_watcher_is_down(self):
        a = self.make_project("alpha")
        b = self.make_project("beta")
        c = self.make_project("gamma")
        dash.watcher_set("alpha", "stop")                # paused from the page
        dash.remember_pause("gamma", True)               # paused, but running again
        self.grepai.alive["beta"] = False                # stopped, not by us

        got = self.report([self.row("alpha", a, False), self.row("beta", b, False),
                           self.row("gamma", c, True)])
        self.assertEqual((got["alpha"]["paused"], got["alpha"]["config_ok"]), (True, True))
        self.assertEqual((got["beta"]["paused"], got["beta"]["config_ok"]), (False, False))
        self.assertEqual((got["gamma"]["paused"], got["gamma"]["config_ok"]), (False, True))

    def test_a_crash_after_a_restart_is_not_dressed_up_as_a_pause(self):
        a = self.make_project("alpha")
        dash.watcher_set("alpha", "stop")
        since = dash.read_paused()["alpha"]
        later = since + dash.PAUSE_GRACE_S + 60          # --refresh started it, then it died
        os.utime(dash.log_path("alpha"), (later, later))
        got = self.report([self.row("alpha", a, False)])
        self.assertEqual((got["alpha"]["paused"], got["alpha"]["config_ok"]), (False, False))


# ------------------------------------------------------------ retire/back ---

class RetireTest(Base):
    def test_retire_takes_the_row_out_and_deletes_nothing(self):
        path = self.make_project("alpha")
        r = dash.retire_project(path)
        self.assertTrue(r["ok"], r)
        self.assertEqual(project.read_registry(self.registry), [])
        self.assertEqual(project.read_registry(self.retired), [("alpha", path)])
        for d in (".grepai", ".gitnexus"):
            self.assertTrue(os.path.isdir(os.path.join(path, d)))
        self.assertFalse(self.grepai.alive["alpha"])
        self.assertIn("alpha", dash.read_paused())

    def test_the_watcher_stopped_is_the_one_code_intel_names(self):
        # .code-intel wins over the registry column, as it does in --status.
        path = self.make_project("alpha", identity_ws="alpha-ws")
        dash.retire_project(path)
        self.assertFalse(self.grepai.alive["alpha-ws"])
        self.assertIn("alpha-ws", dash.read_paused())
        self.assertEqual(project.read_registry(self.retired), [("alpha", path)])

    def test_a_path_outside_the_registry_is_refused(self):
        self.make_project("alpha")
        r = dash.retire_project("/somewhere/else")
        self.assertFalse(r["ok"])
        self.assertEqual(len(project.read_registry(self.registry)), 1)

    def test_a_watcher_that_will_not_stop_does_not_block_retiring(self):
        path = self.make_project("alpha")
        self.grepai.stuck.add("alpha")
        r = dash.retire_project(path)
        self.assertTrue(r["ok"])
        self.assertIn("would not stop", r["message"])
        self.assertEqual(project.read_registry(self.retired), [("alpha", path)])
        rows = dash.read_retired()
        self.assertEqual([(x["workspace"], x["watcher"]) for x in rows], [("alpha", True)])

    def test_retirements_finishing_together_lose_no_project(self):
        paths = [self.make_project("p%02d" % i) for i in range(12)]
        barrier = threading.Barrier(len(paths))
        real_set = dash.watcher_set

        def slow_stop(ws, action):                     # every stop returns at once
            r = real_set(ws, action)
            barrier.wait(timeout=10)
            return r

        with mock.patch.object(dash, "watcher_set", slow_stop):
            threads = [threading.Thread(target=dash.retire_project, args=(p,)) for p in paths]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        self.assertEqual(project.read_registry(self.registry), [])
        self.assertEqual(sorted(p for _, p in project.read_registry(self.retired)), sorted(paths))

    def test_bringing_back_restores_the_row_and_leaves_it_paused(self):
        path = self.make_project("alpha")
        dash.retire_project(path)
        r = dash.restore_project(path)
        self.assertTrue(r["ok"], r)
        self.assertIn("still paused", r["message"])
        self.assertEqual(project.read_registry(self.registry), [("alpha", path)])
        self.assertEqual(project.read_registry(self.retired), [])
        self.assertFalse(self.grepai.alive["alpha"])
        self.assertTrue(dash.pause_holds("alpha", dash.read_paused().get("alpha")))

    def test_a_project_retired_before_pause_notes_comes_back_paused(self):
        path = self.make_project("alpha", running=False)
        project.registry_delete(self.registry, path)          # retired by an older page
        project.registry_add(self.retired, "alpha", path)
        self.assertEqual(dash.read_paused(), {})
        r = dash.restore_project(path)
        self.assertIn("still paused", r["message"])
        self.assertTrue(dash.pause_holds("alpha", dash.read_paused().get("alpha")))

    def test_bringing_back_says_so_when_the_watcher_never_stopped(self):
        path = self.make_project("alpha")
        self.grepai.stuck.add("alpha")
        dash.retire_project(path)
        r = dash.restore_project(path)
        self.assertIn("watcher is running", r["message"])

    def test_bringing_back_refuses_unknown_and_vanished_projects(self):
        path = self.make_project("alpha")
        self.assertFalse(dash.restore_project(path)["ok"])       # not retired
        dash.retire_project(path)
        shutil.rmtree(path)
        r = dash.restore_project(path)
        self.assertFalse(r["ok"])
        self.assertIn("no longer exists", r["error"])
        self.assertEqual(project.read_registry(self.registry), [])

    def test_a_retired_row_re_applied_from_the_cli_is_live_again(self):
        path = self.make_project("alpha")
        dash.retire_project(path)
        project.registry_add(self.registry, "renamed", path)      # --apply ran again
        self.assertEqual(dash.read_retired(), [])
        # Bringing it back now drops the stale row and leaves the live one alone.
        r = dash.restore_project(path)
        self.assertTrue(r["ok"])
        self.assertIn("already back", r["message"])
        self.assertEqual(project.read_registry(self.registry), [("renamed", path)])
        self.assertEqual(project.read_registry(self.retired), [])


# ------------------------------------------------------------------ gates ---

class GateTest(Base):
    """The gates in front of every request, over a real loopback socket."""

    def setUp(self):
        super().setUp()
        self.srv = dash.http.server.ThreadingHTTPServer(("127.0.0.1", 0), dash.Handler)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def send(self, method="POST", path="/api/watcher", body=None, headers=None):
        # By default an invalid action, refused before anything runs.
        data = json.dumps(body if body is not None else {"ws": "alpha", "action": "bogus"}).encode()
        h = {"Content-Type": "application/json", "X-Code-Intel": "dash"}
        h.update(headers or {})
        h = {k: v for k, v in h.items() if v is not None}
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path),
                                     data=data if method == "POST" else None,
                                     headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            with e:
                return e.code, e.read().decode()

    def test_a_request_from_this_page_gets_through(self):
        code, body = self.send()
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["error"], "action must be stop or start")

    def test_the_custom_header_is_required(self):
        code, body = self.send(headers={"X-Code-Intel": None})
        self.assertEqual((code, json.loads(body)["error"]), (403, "missing X-Code-Intel header"))

    def test_a_foreign_origin_is_refused(self):
        code, body = self.send(headers={"Origin": "https://example.com"})
        self.assertEqual(code, 403)
        self.assertIn("cross-origin", json.loads(body)["error"])

    def test_an_opaque_origin_is_refused(self):
        code, _ = self.send(headers={"Origin": "null"})
        self.assertEqual(code, 403)

    def test_a_rebound_host_name_is_refused_for_writes_and_reads(self):
        rebound = {"Host": "attacker.example:%d" % self.port}
        code, body = self.send(headers=rebound)
        self.assertEqual(code, 403)
        self.assertIn("unexpected Host", json.loads(body)["error"])
        for path in ("/", "/api/status", "/api/search?ws=alpha&q=x", "/api/log?ws=alpha"):
            code, _ = self.send(method="GET", path=path, headers=rebound)
            self.assertEqual(code, 403, path)
        self.assertEqual(self.grepai.calls, [])

    def test_a_preflight_is_never_answered(self):
        code, _ = self.send(method="OPTIONS")
        self.assertEqual(code, 501)

    def test_an_oversized_or_malformed_body_is_empty(self):
        code, body = self.send(body={"ws": "a" * 9000, "action": "stop"})
        self.assertEqual((code, json.loads(body)["error"]), (200, "action must be stop or start"))
        code, body = self.send(path="/api/project", body=["not", "an", "object"])
        self.assertEqual((code, json.loads(body)["error"]), (200, "project path missing"))

    def test_an_unknown_write_is_not_found(self):
        code, _ = self.send(path="/api/nothing")
        self.assertEqual(code, 404)

    def test_a_write_that_raises_still_answers(self):
        path = self.make_project("alpha")
        with mock.patch.object(project, "registry_add", side_effect=OSError("disk full")):
            code, body = self.send(path="/api/project", body={"action": "retire", "path": path})
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body), {"ok": False, "error": "the action failed: disk full"})

    def test_a_malformed_workspace_is_refused_on_reads(self):
        for path in ("/api/search?ws=../x&q=hi", "/api/log?ws=-rf", "/api/files?ws=a%20b"):
            code, body = self.send(method="GET", path=path)
            self.assertEqual((code, json.loads(body)["error"]), (200, "workspace name malformed"), path)
        self.assertEqual(self.grepai.calls, [])

    def test_the_index_is_read_from_qdrant_as_reported_never_from_the_request(self):
        seen = []
        with mock.patch.object(dash, "collection_files",
                               lambda url, col: seen.append((url, col)) or {"ok": True}):
            code, body = self.send(method="GET", path="/api/files?ws=alpha&url=http://evil.example/")
            self.assertEqual(json.loads(body)["error"], "no qdrant URL yet — reload the page")
            dash._last_status["doc"] = {"svc": {"qdrant": {"http_url": "http://127.0.0.1:6333"}}}
            self.send(method="GET", path="/api/files?ws=alpha&url=http://evil.example/")
        self.assertEqual(seen, [("http://127.0.0.1:6333", "workspace_alpha")])

    def test_a_query_is_never_read_as_a_flag(self):
        self.send(method="GET", path="/api/search?ws=alpha&q=--workspace%20other")
        search = [c for c in self.grepai.calls if c[:2] == ["grepai", "search"]]
        self.assertEqual(search, [["grepai", "search", "--workspace", "alpha", "--json",
                                   "-n", "10", "--", "--workspace other"]])


if __name__ == "__main__":
    unittest.main()
