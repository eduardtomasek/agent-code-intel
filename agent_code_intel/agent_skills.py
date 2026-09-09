"""Repo-scoped agent routing skill lifecycle.

The canonical asset ships inside the Python package so the self-installed CLI
can materialize the same bytes for Claude and Codex. Importing this module does
no I/O; callers explicitly request every read or write.
"""

from __future__ import annotations

import os
import tempfile

from .config import CliError

SKILL_NAME = "agent-code-intel-routing"
MANAGED_MARKER = "<!-- agent-code-intel:managed -->"

_TARGET_DIRS = {
    "claude": os.path.join(".claude", "skills", SKILL_NAME),
    "codex": os.path.join(".agents", "skills", SKILL_NAME),
}


def source_path() -> str:
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "assets",
        SKILL_NAME,
        "SKILL.md",
    )


def source_text() -> str:
    try:
        with open(source_path(), encoding="utf-8") as handle:
            return handle.read()
    except OSError as exc:
        raise CliError("could not read routing skill asset: %s" % exc)


def target_paths(root: str, agent_target: str = "both") -> tuple[tuple[str, str], ...]:
    agents = ("claude", "codex") if agent_target == "both" else (agent_target,)
    return tuple(
        (agent, os.path.join(root, _TARGET_DIRS[agent], "SKILL.md"))
        for agent in agents
    )


def relative_path(agent: str) -> str:
    return os.path.join(_TARGET_DIRS[agent], "SKILL.md")


def state(path: str, desired: str | None = None) -> str:
    if not os.path.lexists(path):
        return "missing"
    if os.path.islink(path) or not os.path.isfile(path):
        return "unsafe"
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            current = handle.read()
    except OSError:
        return "unsafe"
    desired = source_text() if desired is None else desired
    if current == desired:
        return "current"
    if MANAGED_MARKER in current:
        return "managed-drift"
    return "foreign"


def validate_targets(root: str, agent_target: str, force: bool) -> None:
    desired = source_text()
    for agent, path in target_paths(root, agent_target):
        unsafe = _unsafe_parent(root, os.path.dirname(path))
        current = "unsafe" if unsafe else state(path, desired)
        if current == "unsafe":
            raise CliError(
                "%s routing skill target is a symlink, unreadable, or not a regular path: %s"
                % (agent, unsafe or path)
            )
        if current == "foreign" and not force:
            raise CliError(
                "%s contains a foreign routing skill: %s; move it or re-run with --force-docs"
                % (agent, path)
            )


def install_targets(
    root: str, agent_target: str, force: bool
) -> tuple[tuple[str, str], ...]:
    validate_targets(root, agent_target, force)
    desired = source_text()
    outcomes: list[tuple[str, str]] = []
    for agent, path in target_paths(root, agent_target):
        current = state(path, desired)
        if current == "current":
            outcomes.append((agent, current))
            continue
        parent = os.path.dirname(path)
        os.makedirs(parent, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=parent, prefix=".SKILL.md.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(desired)
            os.chmod(temporary, 0o644)
            os.replace(temporary, path)
        except OSError as exc:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise CliError("could not install routing skill %s: %s" % (path, exc))
        outcomes.append((agent, "installed" if current == "missing" else "updated"))
    return tuple(outcomes)


def remove_managed_targets(root: str) -> tuple[tuple[str, str], ...]:
    outcomes: list[tuple[str, str]] = []
    desired = source_text()
    for agent, path in target_paths(root, "both"):
        current = state(path, desired)
        if current not in ("current", "managed-drift"):
            continue
        try:
            os.unlink(path)
            _remove_empty_parents(os.path.dirname(path), root)
        except OSError as exc:
            raise CliError("could not remove routing skill %s: %s" % (path, exc))
        outcomes.append((agent, path))
    return tuple(outcomes)


def managed_targets(root: str) -> tuple[tuple[str, str], ...]:
    desired = source_text()
    return tuple(
        (agent, path)
        for agent, path in target_paths(root, "both")
        if state(path, desired) in ("current", "managed-drift")
    )


def status(root: str, agent_target: str) -> dict[str, dict[str, object]]:
    desired = source_text()
    result: dict[str, dict[str, object]] = {}
    for agent, path in target_paths(root, agent_target):
        current = state(path, desired)
        result[agent] = {
            "path": relative_path(agent),
            "state": current,
            "ok": current == "current",
        }
    return result


def _unsafe_parent(root: str, parent: str) -> str | None:
    relative = os.path.relpath(parent, root)
    if relative == os.pardir or relative.startswith(os.pardir + os.sep):
        return parent
    current = root
    for part in relative.split(os.sep):
        if part in ("", os.curdir):
            continue
        current = os.path.join(current, part)
        if os.path.lexists(current) and (
            os.path.islink(current) or not os.path.isdir(current)
        ):
            return current
    return None


def _remove_empty_parents(path: str, root: str) -> None:
    while path != root and os.path.commonpath((root, path)) == root:
        try:
            os.rmdir(path)
        except OSError:
            return
        path = os.path.dirname(path)
