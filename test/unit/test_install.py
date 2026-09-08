"""Install and upgrade — issue #52 (issue #48 decisions 56–67; issues #39, #40).

Covers ledger rows INST-1…INST-12 and TOL-6 at the unit layer: the whole-tree
lib swap and its guards, the absolute-shebang launcher with a
location-relative package path, the native ``_install_claude_permission``
port, the ``defaults.toml`` template, and :func:`agent_code_intel.install.run`
end to end over a throwaway ``HOME`` (including a real subprocess run of the
installed launcher from an unrelated directory with a poisoned ``PYTHONPATH``).

No stack, no network — every case runs against a real temp tree.
"""

import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_code_intel import __version__, config, install
from agent_code_intel.commands import Reporter
from agent_code_intel.config import CliError


def _reporter():
    out, err = io.StringIO(), io.StringIO()
    return Reporter(out, err), out, err


class Base(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="aci-install-")
        self.bin = os.path.join(self.home, ".local", "bin")
        self.lib = os.path.join(self.home, ".local", "lib", "agent-code-intel")
        self.conf = os.path.join(self.home, ".config", "code-intel")

    def marker(self, lib=None):
        return os.path.join(lib or self.lib, "agent_code_intel", "__init__.py")


# --------------------------------------------------------------- lib step ---


class LibStep(Base):
    def test_clean_install_copies_the_whole_package(self):
        self.assertIs(install._install_lib(self.lib), True)
        self.assertTrue(os.path.isfile(self.marker()))
        installed = sorted(
            p.name for p in Path(self.lib, "agent_code_intel").glob("*.py")
        )
        source = sorted(
            p.name for p in Path(install._source_package()).glob("*.py")
        )
        self.assertEqual(installed, source)

    def test_no_pycache_in_the_installed_tree(self):
        install._install_lib(self.lib)
        self.assertEqual(
            list(Path(self.lib).rglob("__pycache__")), [], "decision 13"
        )

    def test_replacing_an_existing_owned_install_swaps_the_whole_tree(self):
        install._install_lib(self.lib)
        # a stale module from an older version must not survive the swap
        stale = os.path.join(self.lib, "agent_code_intel", "legacy_gone.py")
        with open(stale, "w") as handle:
            handle.write("# from an older version\n")
        self.assertIs(install._install_lib(self.lib), True)
        self.assertFalse(os.path.exists(stale), "decision 4 — vanished module")
        self.assertTrue(os.path.isfile(self.marker()))

    def test_running_from_the_installed_copy_skips_the_lib_step(self):
        install._install_lib(self.lib)
        with mock.patch.object(
            install,
            "_source_package",
            return_value=os.path.join(self.lib, "agent_code_intel"),
        ):
            self.assertIs(install._install_lib(self.lib), False)

    def test_a_symlink_at_the_lib_path_is_a_hard_error(self):
        os.makedirs(os.path.dirname(self.lib))
        target = tempfile.mkdtemp(prefix="aci-symlink-target-")
        os.symlink(target, self.lib)
        with self.assertRaises(CliError) as caught:
            install._install_lib(self.lib)
        # one generic lib-step message — issue #40 decision 14
        self.assertEqual(
            str(caught.exception),
            "could not install %s: it is a symlink or is not an "
            "agent-code-intel install (no agent_code_intel/__init__.py)" % self.lib,
        )
        self.assertTrue(os.path.islink(self.lib), "nothing deleted")

    def test_foreign_content_at_the_lib_path_is_a_hard_error(self):
        os.makedirs(self.lib)
        with open(os.path.join(self.lib, "someone-elses-file"), "w") as handle:
            handle.write("hands off\n")
        with self.assertRaises(CliError) as caught:
            install._install_lib(self.lib)
        self.assertEqual(
            str(caught.exception),
            "could not install %s: it is a symlink or is not an "
            "agent-code-intel install (no agent_code_intel/__init__.py)" % self.lib,
        )
        self.assertTrue(
            os.path.isfile(os.path.join(self.lib, "someone-elses-file")),
            "nothing deleted",
        )

    def test_leftover_new_and_old_from_a_crash_are_cleaned_first(self):
        os.makedirs(self.lib + ".new")
        os.makedirs(self.lib + ".old")
        with open(os.path.join(self.lib + ".new", "junk"), "w") as handle:
            handle.write("x")
        install._install_lib(self.lib)
        self.assertFalse(os.path.exists(self.lib + ".new"))
        self.assertFalse(os.path.exists(self.lib + ".old"))
        self.assertTrue(os.path.isfile(self.marker()))

    def test_a_failed_final_rename_restores_the_old_tree_and_reports(self):
        install._install_lib(self.lib)  # a working install to overwrite
        original = Path(self.marker()).read_text()

        real_rename = os.rename

        def flaky(src, dst):
            if src == self.lib + ".new":
                raise OSError("disk full")
            return real_rename(src, dst)

        with mock.patch("os.rename", side_effect=flaky):
            with self.assertRaises(CliError) as caught:
                install._install_lib(self.lib)
        self.assertIn("could not install", str(caught.exception))
        self.assertTrue(os.path.isfile(self.marker()), "old install put back")
        self.assertEqual(Path(self.marker()).read_text(), original)
        self.assertFalse(os.path.exists(self.lib + ".new"))
        self.assertFalse(os.path.exists(self.lib + ".old"))

    def test_a_failed_copy_is_a_hard_error_naming_the_path(self):
        with mock.patch("shutil.copytree", side_effect=OSError("nope")):
            with self.assertRaises(CliError) as caught:
                install._install_lib(self.lib)
        self.assertEqual(
            str(caught.exception), "could not install %s: nope" % self.lib
        )
        self.assertFalse(os.path.exists(self.lib))
        self.assertFalse(os.path.exists(self.lib + ".new"))


# ------------------------------------------------------------ launcher step -


class LauncherStep(Base):
    def setUp(self):
        super().setUp()
        os.makedirs(self.bin)

    def path(self):
        return os.path.join(self.bin, "agent-code-intel")

    def test_writes_an_executable_launcher_with_an_absolute_shebang(self):
        rep, out, _ = _reporter()
        install._install_launcher(self.bin, self.lib, None, rep)
        text = Path(self.path()).read_text()
        self.assertEqual(
            text.splitlines()[0], "#!" + sys.executable, "issue #48 decision 2"
        )
        self.assertIn(install.RUNTIME_GATE.rstrip("\n"), text)
        self.assertTrue(os.stat(self.path()).st_mode & stat.S_IXUSR)
        self.assertEqual(out.getvalue(), "installed -> %s\n" % self.path())

    def test_package_path_is_relative_to_the_launcher_not_baked_absolute(self):
        # issue #39 decision 6 — survives a symlinked launcher, no $HOME assumption
        rep, _, _ = _reporter()
        install._install_launcher(self.bin, self.lib, None, rep)
        text = Path(self.path()).read_text()
        self.assertIn("os.path.dirname(os.path.realpath(__file__))", text)
        self.assertIn('"..", "lib", "agent-code-intel"', text)
        self.assertNotIn(self.lib, text, "no absolute lib path baked in")

    def test_overwrites_a_v3_bash_launcher_in_place(self):
        with open(self.path(), "w") as handle:
            handle.write("#!/usr/bin/env bash\n# the old v3 script\n")
        rep, _, _ = _reporter()
        install._install_launcher(self.bin, self.lib, None, rep)
        self.assertTrue(
            Path(self.path()).read_text().startswith("#!" + sys.executable)
        )

    def test_running_from_the_installed_launcher_skips_and_says_already(self):
        with open(self.path(), "w") as handle:
            handle.write("#!x\n")
        rep, out, _ = _reporter()
        install._install_launcher(self.bin, self.lib, self.path(), rep)
        self.assertEqual(Path(self.path()).read_text(), "#!x\n", "left untouched")
        self.assertEqual(
            out.getvalue(), "already installed at %s\n" % self.path()
        )

    def test_no_stray_temp_file_left_behind(self):
        rep, _, _ = _reporter()
        install._install_launcher(self.bin, self.lib, None, rep)
        self.assertEqual(
            [p.name for p in Path(self.bin).iterdir()], ["agent-code-intel"]
        )


# ------------------------------------------------------- permission rule ----


class ClaudePermission(Base):
    def settings(self):
        return os.path.join(self.home, ".claude", "settings.json")

    def allow(self):
        with open(self.settings()) as handle:
            return json.load(handle)["permissions"]["allow"]

    def run_it(self):
        rep, out, _ = _reporter()
        install._install_claude_permission(self.home, rep)
        return out.getvalue()

    def test_clean_run_adds_exactly_one_unstarred_rule(self):
        out = self.run_it()
        self.assertEqual(self.allow(), ["Bash(agent-code-intel --refresh)"])
        self.assertIn(
            "claude: allowed Bash(agent-code-intel --refresh) in", out
        )

    def test_second_run_is_idempotent(self):
        self.run_it()
        out = self.run_it()
        self.assertEqual(self.allow(), ["Bash(agent-code-intel --refresh)"])
        self.assertIn("already allowed", out)

    def test_removes_the_two_legacy_refresh_intel_rules_and_keeps_the_rest(self):
        os.makedirs(os.path.dirname(self.settings()))
        with open(self.settings(), "w") as handle:
            json.dump(
                {
                    "permissions": {
                        "allow": [
                            "Bash(./refresh-intel.sh)",
                            "Bash(./refresh-intel.sh *)",
                            "Bash(git status)",
                        ]
                    }
                },
                handle,
            )
        out = self.run_it()
        self.assertEqual(
            self.allow(),
            ["Bash(git status)", "Bash(agent-code-intel --refresh)"],
        )
        self.assertIn("removed legacy", out)

    def test_unreadable_json_is_left_untouched_with_guidance(self):
        os.makedirs(os.path.dirname(self.settings()))
        with open(self.settings(), "w") as handle:
            handle.write("not valid json{")
        out = self.run_it()
        self.assertEqual(Path(self.settings()).read_text(), "not valid json{")
        self.assertIn("not readable JSON", out)
        self.assertIn("Add these to permissions.allow by hand", out)

    def test_a_non_list_allow_is_left_untouched(self):
        os.makedirs(os.path.dirname(self.settings()))
        with open(self.settings(), "w") as handle:
            json.dump({"permissions": {"allow": "oops"}}, handle)
        out = self.run_it()
        self.assertIn("is not a list", out)
        with open(self.settings()) as handle:
            self.assertEqual(
                json.load(handle), {"permissions": {"allow": "oops"}}
            )


# --------------------------------------------------------- config template --


class ConfigTemplate(unittest.TestCase):
    def test_template_has_all_thirteen_keys_at_their_defaults(self):
        template = config.DEFAULTS_TOML_TEMPLATE
        # Every key line is commented, so a fresh parse is empty …
        self.assertEqual(tomllib.loads(template), {})
        # … and uncommenting every key round-trips to the built-in Config.
        uncommented = "\n".join(
            line[1:] if line.startswith("#") and "=" in line else line
            for line in template.splitlines()
        )
        raw = tomllib.loads(uncommented)
        self.assertEqual(len(raw), 13)
        want = config.default_config()
        self.assertEqual(raw["chunk_size"], int(want.chunk_size))
        self.assertEqual(raw["qdrant_host"], want.qdrant_host)
        self.assertEqual(tuple(raw["extra_ignores"]), want.extra_ignores)
        self.assertEqual(tuple(raw["gitignore_entries"]), want.gitignore_entries)


# --------------------------------------------------------------- run() ------


class Run(Base):
    def do_run(self, *, config_source="defaults", write_perms=True, path="",
               source_launcher="/nowhere/agent-code-intel.py"):
        os.makedirs(self.conf, exist_ok=True)
        rep, out, err = _reporter()
        code = install.run(
            home=self.home,
            conf_dir=self.conf,
            config_source=config_source,
            write_perms=write_perms,
            path=path,
            source_launcher=source_launcher,
            reporter=rep,
        )
        return code, out.getvalue(), err.getvalue()

    def test_clean_install_prints_every_line_in_order(self):
        code, out, err = self.do_run(path="/usr/bin:/bin")
        self.assertEqual((code, err), (0, ""))
        toml_path = os.path.join(self.conf, "defaults.toml")
        settings = os.path.join(self.home, ".claude", "settings.json")
        self.assertEqual(
            out,
            "installed -> %s\n" % self.lib
            + "installed -> %s\n" % os.path.join(self.bin, "agent-code-intel")
            + "WARNING: ~/.local/bin is not on PATH. Add to your shell rc:\n"
            + '  export PATH="$HOME/.local/bin:$PATH"\n'
            + "wrote %s\n" % toml_path
            + "claude: allowed Bash(agent-code-intel --refresh) in %s\n" % settings
            + "        (so Claude Code can run it after a task without asking "
            "every time)\n",
        )
        self.assertTrue(os.access(os.path.join(self.bin, "agent-code-intel"), os.X_OK))
        self.assertTrue(os.path.isfile(self.marker()))
        self.assertTrue(os.path.isfile(toml_path))

    def test_installed_command_runs_standalone_from_an_unrelated_cwd(self):
        # issue #52 AC3 / INST-11 — the installed launcher works with no
        # checkout on sys.path, from another directory, resisting a poisoned
        # PYTHONPATH.
        self.do_run()
        elsewhere = tempfile.mkdtemp(prefix="aci-elsewhere-")
        poison = tempfile.mkdtemp(prefix="aci-poison-")
        os.makedirs(os.path.join(poison, "agent_code_intel"))
        with open(os.path.join(poison, "agent_code_intel", "__init__.py"), "w") as h:
            h.write("raise SystemExit('poisoned PYTHONPATH won')\n")
        proc = subprocess.run(
            [os.path.join(self.bin, "agent-code-intel"), "--version"],
            cwd=elsewhere,
            capture_output=True,
            text=True,
            env={"HOME": self.home, "PATH": "/usr/bin:/bin", "PYTHONPATH": poison},
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "agent-code-intel %s\n" % __version__)

    def test_no_perms_skips_the_settings_file(self):
        _, out, _ = self.do_run(write_perms=False)
        self.assertIn("skipped the Claude Code permission rule (--no-perms)", out)
        self.assertFalse(
            os.path.exists(os.path.join(self.home, ".claude", "settings.json"))
        )

    def test_env_config_is_kept_and_no_toml_is_written(self):
        _, out, _ = self.do_run(config_source="env")
        self.assertIn(
            "kept %s (defaults.toml not written; see --help)"
            % os.path.join(self.conf, "defaults.env"),
            out,
        )
        self.assertFalse(os.path.exists(os.path.join(self.conf, "defaults.toml")))

    def test_existing_toml_config_is_left_silent(self):
        _, out, _ = self.do_run(config_source="toml")
        self.assertNotIn("wrote", out)
        self.assertNotIn("kept", out)

    def test_path_advisory_switches_on_membership(self):
        _, off, _ = self.do_run(path="/usr/bin:/bin")
        self.assertIn("is not on PATH", off)
        _, on, _ = self.do_run(path="%s:/usr/bin" % self.bin)
        self.assertIn("%s is on PATH" % self.bin, on)

    def test_v2_upgrade_removes_the_code_intel_init_binary(self):
        os.makedirs(self.bin)
        old = os.path.join(self.bin, "code-intel-init")
        with open(old, "w") as handle:
            handle.write("#!/usr/bin/env bash\n")
        _, out, _ = self.do_run()
        self.assertFalse(os.path.exists(old))
        self.assertIn("removed old binary -> %s" % old, out)

    def test_dashboard_warning_only_when_a_dashboard_sits_alongside(self):
        os.makedirs(self.bin)
        with open(os.path.join(self.bin, "code-intel-dash"), "w") as handle:
            handle.write("#!/bin/sh\n")
        _, out, _ = self.do_run()
        self.assertIn("code-intel-dash also needs reinstalling", out)

    def test_from_installed_copy_says_already_installed_at_the_bin_path(self):
        # issue #39 decision 14 / issue #40 decision 12 — `already installed at
        # $DEST` unchanged (DEST is the bin launcher), then the rest still runs.
        self.do_run()
        installed_launcher = os.path.join(self.bin, "agent-code-intel")
        with mock.patch.object(
            install,
            "_source_package",
            return_value=os.path.join(self.lib, "agent_code_intel"),
        ):
            _, out, err = self.do_run(source_launcher=installed_launcher)
        self.assertEqual(err, "")
        self.assertIn("already installed at %s" % installed_launcher, out)
        self.assertNotIn("installed -> ", out)
        self.assertIn("claude: agent-code-intel --refresh already allowed", out)

    def test_step_order_is_lib_then_bin_then_config_then_permission(self):
        _, out, _ = self.do_run()
        lines = out.splitlines()
        i_lib = lines.index("installed -> %s" % self.lib)
        i_bin = lines.index(
            "installed -> %s" % os.path.join(self.bin, "agent-code-intel")
        )
        i_cfg = next(n for n, l in enumerate(lines) if l.startswith("wrote "))
        i_perm = next(n for n, l in enumerate(lines) if l.startswith("claude: "))
        self.assertLess(i_lib, i_bin)
        self.assertLess(i_bin, i_cfg)
        self.assertLess(i_cfg, i_perm)

    def test_a_foreign_lib_dir_aborts_before_writing_anything(self):
        os.makedirs(self.lib)
        with open(os.path.join(self.lib, "foreign"), "w") as handle:
            handle.write("x")
        with self.assertRaises(CliError):
            self.do_run()
        self.assertFalse(
            os.path.exists(os.path.join(self.bin, "agent-code-intel"))
        )
        self.assertFalse(os.path.exists(os.path.join(self.conf, "defaults.toml")))


if __name__ == "__main__":
    unittest.main()
