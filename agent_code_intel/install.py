"""install — self-install, upgrade from v2/v3, and the launcher templates.

Two things live here:

* the launcher templates (issue #50) — both the source launcher checked in at
  the repo root and the launcher ``--install`` writes carry the *same* inline
  Python-3.11 gate (issue #50, acceptance criterion 1). Keeping the gate here
  as one string and rendering both launchers from it is how "identical" is
  guaranteed rather than hoped for;

* the install / upgrade machinery (issue #52; issue #48, decisions 56–67;
  issues #39, #40). :func:`run` writes a thin launcher into ``~/.local/bin``
  and the whole package bundle into ``~/.local/lib/agent-code-intel`` (the lib
  dir holds an importable package but is not itself one), preserving existing
  config and registry, installing the dashboard from its own version, and
  idempotently cleaning up the v2/v3
  ``code-intel-init`` name and its two legacy permission rules. The step order
  is lib → launcher → old-name → PATH check → dashboard → config
  template → permission rule (issue #40 §3); transactionality ends at the
  launcher, so a later failure can leave a working CLI just as the reference
  does.

``install`` depends only on :mod:`agent_code_intel.config` (decision 34); the
:class:`~agent_code_intel.commands.Reporter` it writes through is constructed
by the caller and passed in.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
from typing import TYPE_CHECKING

from . import config
from .config import CliError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .commands import Reporter

# The inline runtime gate. It runs *before* the ``agent_code_intel`` package is
# imported, so it must parse and execute under Python 3.9 (the oldest
# interpreter a stock macOS is likely to reach for) — no f-strings with ``=``,
# no ``match``, no ``tomllib``, nothing 3.10+. On an interpreter below 3.11 it
# prints the approved one-line diagnostic (issue #48, decision 3; issue #35,
# TXT-2) and exits 1 with no traceback.
RUNTIME_GATE = '''\
import sys as _sys

if _sys.version_info < (3, 11):
    _v = _sys.version_info
    _sys.stderr.write(
        "[ERROR: agent-code-intel requires Python 3.11 or newer "
        "(found %d.%d.%d)]\\n" % (_v[0], _v[1], _v[2])
    )
    raise SystemExit(1)
'''

_LAUNCHER_BODY = '''\
"""agent-code-intel — thin launcher: gate the interpreter, then hand off.

Generated from ``agent_code_intel.install.render_launcher``. Do not edit by
hand; edit the template and regenerate (``test/unit/test_launcher.py`` checks
this file still matches).
"""

{gate}

import os
import sys

sys.path.insert(0, {package_parent})

from agent_code_intel.cli import main

raise SystemExit(
    main(sys.argv[1:], os.environ, os.getcwd(), sys.stdout, sys.stderr)
)
'''

# How each launcher locates the importable ``agent_code_intel`` package
# (issue #48, decision 2 / issue #39):
#   source     — the package sits next to this file in the checkout
#   installed  — an absolute lib directory the installer bakes in
_SOURCE_PACKAGE_PARENT = "os.path.dirname(os.path.realpath(__file__))"
_DASHBOARD_NAME = "code-intel-dash"
_DASHBOARD_VERSION_RE = re.compile(
    r"^VERSION\s*=\s*[\"']([^\"']+)[\"']\s*$", re.MULTILINE
)


def render_launcher(shebang: str, package_parent: str = _SOURCE_PACKAGE_PARENT) -> str:
    """Return the full text of a launcher.

    ``shebang`` is the first line (``#!/usr/bin/env python3`` for the source
    launcher; an absolute ``#!<sys.executable>`` for the installed one, issue
    #48 decision 2). ``package_parent`` is a Python expression that evaluates
    to the directory containing the ``agent_code_intel`` package.
    """

    return shebang.rstrip("\n") + "\n" + _LAUNCHER_BODY.format(
        gate=RUNTIME_GATE.rstrip("\n"),
        package_parent=package_parent,
    )


SOURCE_LAUNCHER = render_launcher("#!/usr/bin/env python3")


# --------------------------------------------------------------- locations --

# Fixed install paths (issue #48, decision 56; issue #39 decisions 2–4). The
# lib dir *holds* the importable ``agent_code_intel`` package and is not itself
# one; the launcher prepends the lib dir to ``sys.path`` and imports from it.
def _bin_dir(home: str) -> str:
    return os.path.join(home, ".local", "bin")


def _lib_dir(home: str) -> str:
    return os.path.join(home, ".local", "lib", "agent-code-intel")


def _source_package() -> str:
    """The checked-out ``agent_code_intel`` directory this module lives in."""
    return os.path.dirname(os.path.abspath(__file__))


def _source_dashboard() -> str:
    """The dashboard bundled beside the source or installed package."""
    return os.path.join(os.path.dirname(_source_package()), _DASHBOARD_NAME)


# The installed launcher locates its package *relative to its own realpath*
# (issue #39 decision 6) — never an absolute path baked in at install time. So
# it survives a symlink to the launcher and does not assume ``bin`` sits under
# ``$HOME``. ``~/.local/bin/agent-code-intel`` → ``…/bin/../lib/agent-code-intel``.
_INSTALLED_PACKAGE_PARENT = (
    'os.path.join(os.path.dirname(os.path.realpath(__file__)), '
    '"..", "lib", "agent-code-intel")'
)


# ---------------------------------------------------------------- the mode --


def run(
    *,
    home: str,
    conf_dir: str,
    config_source: str,
    write_perms: bool,
    path: str,
    source_launcher: str | None,
    reporter: Reporter,
) -> int:
    """The ``--install`` mode — the sequence in issue #40 §3.

    ``config_source`` is :attr:`LoadedConfig.source` — ``"defaults"`` (neither
    config file exists → drop the TOML template), ``"env"`` (a ``defaults.env``
    exists → keep it, write nothing) or ``"toml"`` (silent). ``source_launcher``
    is the absolute path of the launcher now running, or ``None`` if it could
    not be resolved; it is only used to recognise ``--install`` from an already
    installed copy (issue #39 decision 14, issue #40 decision 12).

    Returns 0 on success. The lib or dashboard steps can raise
    :class:`~agent_code_intel.config.CliError` (``[ERROR: …]``, exit 1, issue
    #40 decision 14) — the caller renders it. Transactionality ends at the
    launcher: a failure in a later step leaves a working CLI, exactly as today.
    """

    bin_dir = _bin_dir(home)
    lib_dir = _lib_dir(home)
    os.makedirs(bin_dir, exist_ok=True)
    os.makedirs(os.path.dirname(lib_dir), exist_ok=True)
    os.makedirs(conf_dir, exist_ok=True)

    # Step order lib → launcher → old-name → PATH check → dashboard
    # (issue #40 decision 9): "new lib + old bash
    # bin" is harmless (bash knows nothing of the lib dir); "new bin + old/no
    # lib" is a broken tool. Each step prints its own reference line; the lib
    # step's `installed -> <lib dir>` is the one new output line (issue #39
    # decision 15 / issue #35 exception 8).
    if _install_lib(lib_dir):
        reporter.say("installed -> %s" % lib_dir)
    _install_launcher(bin_dir, lib_dir, source_launcher, reporter)

    _remove_old_name(bin_dir, source_launcher, reporter)
    _check_path(home, path, reporter)
    _install_dashboard(bin_dir, reporter)
    _write_config_template(conf_dir, config_source, reporter)

    if write_perms:
        _install_claude_permission(home, reporter)
    else:
        reporter.say("skipped the Claude Code permission rule (--no-perms)")

    return 0


# --------------------------------------------------------------- lib step ---


def _install_lib(lib_dir: str) -> bool:
    """Replace ``~/.local/lib/agent-code-intel`` as a whole (issue #40
    decisions 4–7, 10; issue #39 decision 13).

    Returns ``True`` if it installed, ``False`` if it skipped (source and
    target resolve to the same tree — ``--install`` from the installed copy,
    issue #40 decision 10). Raises :class:`CliError` — the one generic lib-step
    error (issue #40 decision 14) — on a symlinked / foreign target or any
    filesystem failure during the swap.
    """

    src = _source_package()
    dst_package = os.path.join(lib_dir, "agent_code_intel")

    # Skip if this IS the installed copy. The lib step has its own path compare
    # (issue #40 decision 10), independent of the launcher's, because this is
    # the step that deletes a directory.
    if os.path.isdir(dst_package) and os.path.realpath(dst_package) == os.path.realpath(src):
        return False

    # Ownership guard before any delete (issue #40 decision 5): replace only a
    # real directory carrying the marker, never a symlink (E1–E3). One message
    # for both failures — decision 14 rejects a bespoke text per case.
    marker = os.path.join(lib_dir, "agent_code_intel", "__init__.py")
    if os.path.islink(lib_dir) or (
        os.path.exists(lib_dir) and not os.path.isfile(marker)
    ):
        raise CliError(
            "could not install %s: it is a symlink or is not an "
            "agent-code-intel install (no agent_code_intel/__init__.py)" % lib_dir
        )

    src_dashboard = _source_dashboard()
    if not os.path.isfile(src_dashboard):
        raise CliError("could not install %s: source dashboard is missing" % lib_dir)

    new = lib_dir + ".new"
    old = lib_dir + ".old"
    _remove_path(new)
    _remove_path(old)  # leftovers from a previous interrupted run (decision 6)

    try:
        os.makedirs(new)
        shutil.copytree(
            src,
            os.path.join(new, "agent_code_intel"),
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        shutil.copy2(src_dashboard, os.path.join(new, _DASHBOARD_NAME))
        if os.path.exists(lib_dir):
            os.rename(lib_dir, old)
            try:
                os.rename(new, lib_dir)
            except OSError:
                # Second rename failed — put the old tree back (decision 7).
                try:
                    os.rename(old, lib_dir)
                except OSError:
                    pass
                raise
        else:
            os.rename(new, lib_dir)
        _remove_path(old)
    except OSError as exc:
        _remove_path(new)
        raise CliError("could not install %s: %s" % (lib_dir, exc))

    return True


def _remove_path(path: str) -> None:
    """Delete ``path`` whether it is a file, a symlink, or a directory."""
    if os.path.islink(path) or os.path.isfile(path):
        os.remove(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)


# ------------------------------------------------------------ launcher step -


def _install_launcher(
    bin_dir: str, lib_dir: str, source_launcher: str | None, reporter: Reporter
) -> None:
    """Write the thin launcher to ``~/.local/bin/agent-code-intel`` (issue #40
    decisions 8, 11, 12) and print the reference's bin-step line unchanged
    (``9406cce`` :380 / :382).

    Absolute shebang on the interpreter running this install (issue #48
    decision 2); the package parent is resolved relative to the launcher's own
    realpath (issue #39 decision 6). Prepared in a temp file in the same
    directory, made executable, swapped in with :func:`os.replace`. No
    ownership guard — the reference overwrites its bin file without one either
    (issue #40 decision 11).
    """

    dst = os.path.join(bin_dir, "agent-code-intel")
    if (
        source_launcher is not None
        and os.path.exists(dst)
        and os.path.realpath(dst) == os.path.realpath(source_launcher)
    ):
        reporter.say("already installed at %s" % dst)
        return

    text = render_launcher(
        "#!" + sys.executable, package_parent=_INSTALLED_PACKAGE_PARENT
    )
    fd, tmp = tempfile.mkstemp(dir=bin_dir, prefix=".agent-code-intel.")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
        os.chmod(tmp, 0o755)
        os.replace(tmp, dst)
    except OSError:
        _remove_path(tmp)
        raise
    reporter.say("installed -> %s" % dst)


# ------------------------------------------------------- the smaller steps --


def _remove_old_name(
    bin_dir: str, source_launcher: str | None, reporter: Reporter
) -> None:
    """Drop the v2/v3 ``code-intel-init`` binary if present (issue #40
    decision 1; ``9406cce`` :386–:391) — a stale copy would keep running under
    the old name from code it no longer matches."""

    old_dest = os.path.join(bin_dir, "code-intel-init")
    if not os.path.lexists(old_dest):
        return
    if source_launcher is not None and os.path.realpath(old_dest) == os.path.realpath(
        source_launcher
    ):
        return
    os.remove(old_dest)
    reporter.say("removed old binary -> %s" % old_dest)


def _check_path(home: str, path: str, reporter: Reporter) -> None:
    """PATH advisory, character-for-character with the reference (``9406cce``
    :392–:397; issue #40 §3 step 5)."""

    entry = os.path.join(home, ".local", "bin")
    if (":" + path + ":").find(":" + entry + ":") != -1:
        reporter.say("%s is on PATH" % entry)
    else:
        reporter.say("WARNING: ~/.local/bin is not on PATH. Add to your shell rc:")
        reporter.say('  export PATH="$HOME/.local/bin:$PATH"')


def _dashboard_version(path: str) -> str:
    """Read the dashboard's own VERSION constant."""

    try:
        with open(path) as handle:
            match = _DASHBOARD_VERSION_RE.search(handle.read())
    except OSError as exc:
        raise CliError("could not read %s: %s" % (path, exc))
    if match is None:
        raise CliError("could not read %s: missing VERSION" % path)
    return match.group(1)


def _install_dashboard(bin_dir: str, reporter: Reporter) -> None:
    """Install the dashboard and keep its own version as the source of truth."""

    src = _source_dashboard()
    version = _dashboard_version(src)
    dst = os.path.join(bin_dir, _DASHBOARD_NAME)

    if os.path.isfile(dst) and os.access(dst, os.X_OK):
        try:
            if _dashboard_version(dst) == version:
                reporter.say(
                    "%s %s already installed at %s"
                    % (_DASHBOARD_NAME, version, dst)
                )
                return
        except CliError:
            pass

    fd, tmp = tempfile.mkstemp(dir=bin_dir, prefix=".%s." % _DASHBOARD_NAME)
    os.close(fd)
    try:
        shutil.copy2(src, tmp)
        os.chmod(tmp, 0o755)
        os.replace(tmp, dst)
    except OSError as exc:
        _remove_path(tmp)
        raise CliError("could not install %s: %s" % (dst, exc))
    reporter.say("installed -> %s (code-intel-dash %s)" % (dst, version))


def _write_config_template(
    conf_dir: str, config_source: str, reporter: Reporter
) -> None:
    """Drop the commented ``defaults.toml`` only when neither config file
    exists; never overwrite or convert an existing config (issue #48 decisions
    10, 23; issue #40 §3 step 7)."""

    if config_source == "defaults":
        toml_path = os.path.join(conf_dir, "defaults.toml")
        with open(toml_path, "w") as handle:
            handle.write(config.DEFAULTS_TOML_TEMPLATE)
        reporter.say("wrote %s" % toml_path)
    elif config_source == "env":
        env_path = os.path.join(conf_dir, "defaults.env")
        reporter.say(
            "kept %s (defaults.toml not written; see --help)" % env_path
        )
    # config_source == "toml": the file is already the target format — silent.


# ---------------------------------------------------- claude permission rule -


def _install_claude_permission(home: str, reporter: Reporter) -> None:
    """Allowlist ``Bash(agent-code-intel --refresh)`` in Claude Code's user
    settings and remove the two legacy ``./refresh-intel.sh`` rules — a native
    port of the embedded ``python3`` block (``9406cce`` :326–:372).

    Merges rather than replaces, never touches a file it cannot parse, writes
    through a temp file, and says exactly what it did.
    """

    new_rules = ["Bash(agent-code-intel --refresh)"]
    old_rules = ["Bash(./refresh-intel.sh)", "Bash(./refresh-intel.sh *)"]
    settings_path = os.path.join(home, ".claude", "settings.json")
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)

    settings: dict = {}
    if os.path.exists(settings_path) and os.path.getsize(settings_path) > 0:
        try:
            with open(settings_path) as handle:
                settings = json.load(handle)
            if not isinstance(settings, dict):
                raise ValueError("not an object")
        except Exception as exc:
            reporter.say(
                "claude: %s is not readable JSON (%s) — left untouched."
                % (settings_path, exc)
            )
            reporter.say(
                "        Add these to permissions.allow by hand: %s"
                % ", ".join(new_rules)
            )
            return

    allow = settings.setdefault("permissions", {}).setdefault("allow", [])
    if not isinstance(allow, list):
        reporter.say(
            "claude: permissions.allow in %s is not a list — left untouched."
            % settings_path
        )
        return

    removed = [rule for rule in old_rules if rule in allow]
    for rule in removed:
        allow.remove(rule)
    added = [rule for rule in new_rules if rule not in allow]
    allow.extend(added)

    if not added and not removed:
        reporter.say(
            "claude: agent-code-intel --refresh already allowed in %s"
            % settings_path
        )
        return

    tmp = settings_path + ".code-intel.tmp"
    with open(tmp, "w") as handle:
        json.dump(settings, handle, indent=2)
        handle.write("\n")
    os.replace(tmp, settings_path)

    if added:
        reporter.say(
            "claude: allowed %s in %s" % (" and ".join(added), settings_path)
        )
        reporter.say(
            "        (so Claude Code can run it after a task without asking "
            "every time)"
        )
    if removed:
        reporter.say(
            "claude: removed legacy %s from %s"
            % (" and ".join(removed), settings_path)
        )
