"""Repo-scoped managed agent skill lifecycle.

The canonical asset ships inside the Python package so the self-installed CLI
can materialize the same bytes for Claude and Codex. Importing this module does
no I/O; callers explicitly request every read or write.
"""

from __future__ import annotations

import os
import tempfile

from .config import CliError

SKILL_NAME = "agent-code-intel-routing"
SKILLS = (SKILL_NAME, "code-context")
MANAGED_MARKER = "<!-- agent-code-intel:managed -->"

_TARGET_DIRS = {
    "claude": os.path.join(".claude", "skills"),
    "codex": os.path.join(".agents", "skills"),
}


def _skill_label(skill_name: str) -> str:
    return (
        "routing skill"
        if skill_name == SKILL_NAME
        else "%s skill" % skill_name
    )


def source_path(skill_name: str = SKILL_NAME) -> str:
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "assets",
        skill_name,
        "SKILL.md",
    )


def source_text(skill_name: str = SKILL_NAME) -> str:
    try:
        with open(source_path(skill_name), encoding="utf-8") as handle:
            return handle.read()
    except OSError as exc:
        raise CliError("could not read %s asset: %s" % (_skill_label(skill_name), exc))


def target_paths(
    root: str, agent_target: str = "both", skill_name: str = SKILL_NAME
) -> tuple[tuple[str, str], ...]:
    agents = ("claude", "codex") if agent_target == "both" else (agent_target,)
    return tuple(
        (agent, os.path.join(root, _TARGET_DIRS[agent], skill_name, "SKILL.md"))
        for agent in agents
    )


def _all_targets(
    root: str, agent_target: str
) -> tuple[tuple[str, str, str], ...]:
    return tuple(
        (skill_name, agent, path)
        for skill_name in SKILLS
        for agent, path in target_paths(root, agent_target, skill_name)
    )


def relative_path(agent: str, skill_name: str = SKILL_NAME) -> str:
    return os.path.join(_TARGET_DIRS[agent], skill_name, "SKILL.md")


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
    desired = {skill_name: source_text(skill_name) for skill_name in SKILLS}
    for skill_name, agent, path in _all_targets(root, agent_target):
        unsafe = _unsafe_parent(root, os.path.dirname(path))
        current = "unsafe" if unsafe else state(path, desired[skill_name])
        label = _skill_label(skill_name)
        if current == "unsafe":
            raise CliError(
                "%s %s target is a symlink, unreadable, or not a regular path: %s"
                % (agent, label, unsafe or path)
            )
        if current == "foreign" and not force:
            raise CliError(
                "%s contains a foreign %s: %s; move it or re-run with --force-docs"
                % (agent, label, path)
            )


def install_targets(
    root: str, agent_target: str, force: bool
) -> tuple[tuple[str, str, str], ...]:
    validate_targets(root, agent_target, force)
    desired = {skill_name: source_text(skill_name) for skill_name in SKILLS}
    outcomes: list[tuple[str, str, str]] = []
    for skill_name, agent, path in _all_targets(root, agent_target):
        current = state(path, desired[skill_name])
        if current == "current":
            outcomes.append((skill_name, agent, current))
            continue
        parent = os.path.dirname(path)
        os.makedirs(parent, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=parent, prefix=".SKILL.md.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(desired[skill_name])
            os.chmod(temporary, 0o644)
            os.replace(temporary, path)
        except OSError as exc:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise CliError(
                "could not install %s %s: %s"
                % (_skill_label(skill_name), path, exc)
            )
        outcomes.append(
            (skill_name, agent, "installed" if current == "missing" else "updated")
        )
    return tuple(outcomes)


def remove_managed_targets(root: str) -> tuple[tuple[str, str, str], ...]:
    outcomes: list[tuple[str, str, str]] = []
    desired = {skill_name: source_text(skill_name) for skill_name in SKILLS}
    for skill_name, agent, path in _all_targets(root, "both"):
        current = state(path, desired[skill_name])
        if current not in ("current", "managed-drift"):
            continue
        try:
            os.unlink(path)
            _remove_empty_parents(os.path.dirname(path), root)
        except OSError as exc:
            raise CliError(
                "could not remove %s %s: %s"
                % (_skill_label(skill_name), path, exc)
            )
        outcomes.append((skill_name, agent, path))
    return tuple(outcomes)


def managed_targets(root: str) -> tuple[tuple[str, str, str], ...]:
    desired = {skill_name: source_text(skill_name) for skill_name in SKILLS}
    return tuple(
        (skill_name, agent, path)
        for skill_name, agent, path in _all_targets(root, "both")
        if state(path, desired[skill_name]) in ("current", "managed-drift")
    )


def status(
    root: str, agent_target: str
) -> dict[str, dict[str, dict[str, object]]]:
    desired = {skill_name: source_text(skill_name) for skill_name in SKILLS}
    result: dict[str, dict[str, dict[str, object]]] = {}
    for skill_name, agent, path in _all_targets(root, agent_target):
        current = state(path, desired[skill_name])
        result.setdefault(agent, {})[skill_name] = {
            "path": relative_path(agent, skill_name),
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
