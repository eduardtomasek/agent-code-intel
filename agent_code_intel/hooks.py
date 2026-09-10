"""Repo-local SessionStart hook lifecycle for Claude and Codex."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass

from .config import CliError

SCRIPT_RELATIVE = os.path.join(".claude", "helpers", "code-context-hint.py")
SETTINGS_RELATIVE = os.path.join(".claude", "settings.json")
CODEX_SETTINGS_RELATIVE = os.path.join(".codex", "hooks.json")
CLAUDE_HOOK_COMMAND = (
    'python3 "${CLAUDE_PROJECT_DIR:-.}/.claude/helpers/code-context-hint.py"'
)
CODEX_HOOK_COMMAND = (
    '/usr/bin/env python3 "$(git rev-parse --show-toplevel)/.claude/helpers/code-context-hint.py"'
)
CLAUDE_HOOK_GROUP = {
    "hooks": [
        {
            "type": "command",
            "command": CLAUDE_HOOK_COMMAND,
            "timeout": 5000,
        }
    ]
}
CODEX_HOOK_GROUP = {
    "hooks": [
        {
            "type": "command",
            "command": CODEX_HOOK_COMMAND,
            "timeout": 5,
        }
    ]
}

_HOOK_SPECS = {
    "claude": (SETTINGS_RELATIVE, CLAUDE_HOOK_COMMAND, 5000),
    "codex": (CODEX_SETTINGS_RELATIVE, CODEX_HOOK_COMMAND, 5),
}


@dataclass(frozen=True)
class InstallResult:
    changed: bool
    warning: str = ""
    registration_changed: bool = False


@dataclass(frozen=True)
class RemoveResult:
    removed: tuple[str, ...]
    warning: str = ""


def source_path() -> str:
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "assets", "code-context-hint.py"
    )


def source_text() -> str:
    try:
        with open(source_path(), encoding="utf-8") as handle:
            return handle.read()
    except OSError as exc:
        raise CliError("could not read SessionStart hook asset: %s" % exc)


def target_names(agent_target: str) -> tuple[str, ...]:
    if agent_target == "both":
        return ("claude", "codex")
    if agent_target in _HOOK_SPECS:
        return (agent_target,)
    raise ValueError("unknown agent target: %s" % agent_target)


def _paths(root: str, agent_target: str = "claude") -> tuple[str, str]:
    settings_relative, _, _ = _HOOK_SPECS[agent_target]
    return os.path.join(root, SCRIPT_RELATIVE), os.path.join(root, settings_relative)


def _canonical_group(agent_target: str = "claude") -> dict[str, object]:
    _, command, timeout = _HOOK_SPECS[agent_target]
    return {"hooks": [{"type": "command", "command": command, "timeout": timeout}]}


def _is_owned_hook(value: object, agent_target: str = "claude") -> bool:
    _, command, _ = _HOOK_SPECS[agent_target]
    return (
        isinstance(value, dict)
        and value.get("type") == "command"
        and value.get("command") == command
    )


def _settings_data(path: str) -> tuple[dict[str, object] | None, str]:
    if not os.path.lexists(path):
        return {}, "missing"
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        return None, "unreadable: %s" % exc
    if not isinstance(value, dict):
        return None, "unreadable: top-level JSON value is not an object"
    return value, "current"


def _session_hooks(settings: dict[str, object]) -> list[object]:
    hooks = settings.get("hooks")
    if hooks is None:
        return []
    if not isinstance(hooks, dict):
        raise ValueError("hooks is not an object")
    session = hooks.get("SessionStart")
    if session is None:
        return []
    if not isinstance(session, list):
        raise ValueError("hooks.SessionStart is not an array")
    return session


def _has_owned_hook(
    settings: dict[str, object], agent_target: str = "claude"
) -> bool:
    for group in _session_hooks(settings):
        if isinstance(group, dict) and isinstance(group.get("hooks", []), list):
            if any(_is_owned_hook(hook, agent_target) for hook in group["hooks"]):
                return True
    return False


def _has_current_hook(
    settings: dict[str, object], agent_target: str = "claude"
) -> bool:
    return _canonical_group(agent_target) in _session_hooks(settings)


def _merge_hook(settings: dict[str, object], agent_target: str = "claude") -> bool:
    if _has_current_hook(settings, agent_target):
        return False

    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("hooks is not an object")
    session = hooks.setdefault("SessionStart", [])
    if not isinstance(session, list):
        raise ValueError("hooks.SessionStart is not an array")

    kept_groups: list[object] = []
    for group in session:
        if not isinstance(group, dict) or not isinstance(group.get("hooks", []), list):
            kept_groups.append(group)
            continue
        foreign_hooks = [
            hook
            for hook in group["hooks"]
            if not _is_owned_hook(hook, agent_target)
        ]
        if len(foreign_hooks) != len(group["hooks"]):
            group = dict(group)
            if foreign_hooks:
                group["hooks"] = foreign_hooks
            else:
                continue
        kept_groups.append(group)

    kept_groups.append(_canonical_group(agent_target))
    hooks["SessionStart"] = kept_groups
    return True


def _remove_hook(settings: dict[str, object], agent_target: str = "claude") -> bool:
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return False
    session = hooks.get("SessionStart")
    if not isinstance(session, list):
        return False

    removed = False
    kept_groups: list[object] = []
    for group in session:
        if not isinstance(group, dict) or not isinstance(group.get("hooks", []), list):
            kept_groups.append(group)
            continue
        foreign_hooks = [
            hook
            for hook in group["hooks"]
            if not _is_owned_hook(hook, agent_target)
        ]
        if len(foreign_hooks) != len(group["hooks"]):
            removed = True
            if foreign_hooks:
                group = dict(group)
                group["hooks"] = foreign_hooks
            else:
                continue
        kept_groups.append(group)

    if not removed:
        return False
    if kept_groups:
        hooks["SessionStart"] = kept_groups
    else:
        hooks.pop("SessionStart", None)
    if not hooks:
        settings.pop("hooks", None)
    return True


def _write_atomic(path: str, text: str) -> bool:
    parent = os.path.dirname(path)
    if os.path.lexists(parent) and (os.path.islink(parent) or not os.path.isdir(parent)):
        raise CliError("hook parent is not a directory: %s" % parent)
    os.makedirs(parent, exist_ok=True)
    if os.path.lexists(path) and (os.path.islink(path) or not os.path.isfile(path)):
        raise CliError("hook target is not a regular file: %s" % path)
    try:
        with open(path, encoding="utf-8") as handle:
            if handle.read() == text:
                return False
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise CliError("could not read hook target %s: %s" % (path, exc))

    fd, temporary = tempfile.mkstemp(dir=parent, prefix=".code-context-hook.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(temporary, 0o755 if path.endswith(".py") else 0o644)
        os.replace(temporary, path)
    except OSError as exc:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise CliError("could not write hook target %s: %s" % (path, exc))
    return True


def _write_settings(path: str, settings: dict[str, object]) -> bool:
    return _write_atomic(path, json.dumps(settings, indent=2, ensure_ascii=False) + "\n")


def install(root: str, agent_target: str = "claude") -> InstallResult:
    script_path = os.path.join(root, SCRIPT_RELATIVE)
    changed = _write_atomic(script_path, source_text())
    warnings: list[str] = []
    registration_changed = False
    for target in target_names(agent_target):
        _, settings_path = _paths(root, target)
        settings, state = _settings_data(settings_path)
        settings_name = os.path.basename(settings_path)
        if settings is None:
            warnings.append(
                "%s is %s; left untouched" % (settings_name, state)
            )
            continue

        try:
            settings_changed = _merge_hook(settings, target)
        except ValueError as exc:
            warnings.append(
                "%s is unreadable: %s; left untouched" % (settings_name, exc)
            )
            continue
        if settings_changed:
            wrote = _write_settings(settings_path, settings)
            registration_changed = wrote or registration_changed
            changed = wrote or changed
    return InstallResult(changed, "; ".join(warnings), registration_changed)


def _file_state(path: str, desired: str) -> str:
    if not os.path.lexists(path):
        return "missing"
    if os.path.islink(path) or not os.path.isfile(path):
        return "unsafe"
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            current = handle.read()
    except OSError:
        return "unsafe"
    return "current" if current == desired else "foreign"


def _status_one(root: str, agent_target: str) -> dict[str, object]:
    script_path, settings_path = _paths(root, agent_target)
    settings, _ = _settings_data(settings_path)
    if settings is None:
        settings_state = "unsafe"
        owned = False
    else:
        try:
            owned = _has_owned_hook(settings, agent_target)
            settings_state = (
                "current"
                if _has_current_hook(settings, agent_target)
                else "managed-drift"
                if owned
                else "missing"
            )
        except ValueError:
            owned = False
            settings_state = "unsafe"

    script_state = _file_state(script_path, source_text())
    if script_state == "foreign" and owned:
        script_state = "managed-drift"

    states = (script_state, settings_state)
    if "unsafe" in states:
        overall = "unsafe"
    elif script_state == "foreign":
        overall = "foreign"
    elif "managed-drift" in states:
        overall = "managed-drift"
    elif all(state == "current" for state in states):
        overall = "current"
    elif all(state == "missing" for state in states):
        overall = "missing"
    else:
        overall = "managed-drift"
    return {
        "path": SCRIPT_RELATIVE,
        "settings_path": _HOOK_SPECS[agent_target][0],
        "script": script_state,
        "settings": settings_state,
        "state": overall,
        "ok": overall == "current",
    }


def _aggregate_state(states: tuple[str, ...]) -> str:
    if "unsafe" in states:
        return "unsafe"
    if "foreign" in states and all(state == "foreign" for state in states):
        return "foreign"
    if all(state == "current" for state in states):
        return "current"
    if all(state == "missing" for state in states):
        return "missing"
    return "managed-drift"


def status(root: str, agent_target: str = "claude") -> dict[str, object]:
    targets = target_names(agent_target)
    if len(targets) == 1:
        return _status_one(root, targets[0])
    agents = {target: _status_one(root, target) for target in targets}
    states = tuple(str(details["state"]) for details in agents.values())
    return {
        "agents": agents,
        "state": _aggregate_state(states),
        "ok": all(bool(details["ok"]) for details in agents.values()),
    }


def _remove_empty_parents(path: str, root: str) -> None:
    while path != root and os.path.commonpath((root, path)) == root:
        try:
            os.rmdir(path)
        except OSError:
            return
        path = os.path.dirname(path)


def _has_any_owned_hook(root: str) -> bool:
    for target in _HOOK_SPECS:
        _, settings_path = _paths(root, target)
        settings, _ = _settings_data(settings_path)
        if settings is not None and _has_owned_hook(settings, target):
            return True
    return False


def remove(root: str, agent_target: str = "claude") -> RemoveResult:
    script_path = os.path.join(root, SCRIPT_RELATIVE)
    removed: list[str] = []
    warning = ""
    owned = False
    for target in target_names(agent_target):
        _, settings_path = _paths(root, target)
        settings, state = _settings_data(settings_path)
        if settings is not None:
            try:
                owned = _has_owned_hook(settings, target) or owned
                if _remove_hook(settings, target):
                    if settings:
                        _write_settings(settings_path, settings)
                    else:
                        os.unlink(settings_path)
                        _remove_empty_parents(os.path.dirname(settings_path), root)
                    removed.append(_HOOK_SPECS[target][0])
            except (OSError, ValueError) as exc:
                warning = "%s could not be updated: %s" % (
                    os.path.basename(settings_path),
                    exc,
                )
        elif os.path.lexists(settings_path):
            warning = "%s is %s; left untouched" % (
                os.path.basename(settings_path),
                state,
            )

    script_state = _file_state(script_path, source_text())
    if (script_state == "current" or owned) and not _has_any_owned_hook(root):
        try:
            os.unlink(script_path)
            removed.append(SCRIPT_RELATIVE)
            _remove_empty_parents(os.path.dirname(script_path), root)
        except OSError as exc:
            raise CliError("could not remove SessionStart hook: %s" % exc)
    return RemoveResult(tuple(removed), warning)
