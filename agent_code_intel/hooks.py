"""Repo-local Claude SessionStart hook lifecycle."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass

from .config import CliError

SCRIPT_RELATIVE = os.path.join(".claude", "helpers", "code-context-hint.py")
SETTINGS_RELATIVE = os.path.join(".claude", "settings.json")
CLAUDE_HOOK_COMMAND = (
    'python3 "${CLAUDE_PROJECT_DIR:-.}/.claude/helpers/code-context-hint.py"'
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


@dataclass(frozen=True)
class InstallResult:
    changed: bool
    warning: str = ""


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


def _paths(root: str) -> tuple[str, str]:
    return os.path.join(root, SCRIPT_RELATIVE), os.path.join(root, SETTINGS_RELATIVE)


def _canonical_group() -> dict[str, object]:
    return {"hooks": [{"type": "command", "command": CLAUDE_HOOK_COMMAND, "timeout": 5000}]}


def _is_owned_hook(value: object) -> bool:
    return (
        isinstance(value, dict)
        and value.get("type") == "command"
        and value.get("command") == CLAUDE_HOOK_COMMAND
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


def _has_owned_hook(settings: dict[str, object]) -> bool:
    for group in _session_hooks(settings):
        if isinstance(group, dict) and isinstance(group.get("hooks", []), list):
            if any(_is_owned_hook(hook) for hook in group["hooks"]):
                return True
    return False


def _has_current_hook(settings: dict[str, object]) -> bool:
    return _canonical_group() in _session_hooks(settings)


def _merge_hook(settings: dict[str, object]) -> bool:
    if _has_current_hook(settings):
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
            hook for hook in group["hooks"] if not _is_owned_hook(hook)
        ]
        if len(foreign_hooks) != len(group["hooks"]):
            group = dict(group)
            if foreign_hooks:
                group["hooks"] = foreign_hooks
            else:
                continue
        kept_groups.append(group)

    kept_groups.append(_canonical_group())
    hooks["SessionStart"] = kept_groups
    return True


def _remove_hook(settings: dict[str, object]) -> bool:
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
            hook for hook in group["hooks"] if not _is_owned_hook(hook)
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


def install(root: str) -> InstallResult:
    script_path, settings_path = _paths(root)
    changed = _write_atomic(script_path, source_text())
    settings, state = _settings_data(settings_path)
    if settings is None:
        return InstallResult(changed, "settings.json is %s; left untouched" % state)

    try:
        settings_changed = _merge_hook(settings)
    except ValueError as exc:
        return InstallResult(
            changed, "settings.json is unreadable: %s; left untouched" % exc
        )
    if settings_changed:
        changed = _write_settings(settings_path, settings) or changed
    return InstallResult(changed)


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


def status(root: str) -> dict[str, object]:
    script_path, settings_path = _paths(root)
    settings, _ = _settings_data(settings_path)
    if settings is None:
        settings_state = "unsafe"
        owned = False
    else:
        try:
            owned = _has_owned_hook(settings)
            settings_state = (
                "current"
                if _has_current_hook(settings)
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
        "settings_path": SETTINGS_RELATIVE,
        "script": script_state,
        "settings": settings_state,
        "state": overall,
        "ok": overall == "current",
    }


def _remove_empty_parents(path: str, root: str) -> None:
    while path != root and os.path.commonpath((root, path)) == root:
        try:
            os.rmdir(path)
        except OSError:
            return
        path = os.path.dirname(path)


def remove(root: str) -> RemoveResult:
    script_path, settings_path = _paths(root)
    removed: list[str] = []
    settings, state = _settings_data(settings_path)
    warning = ""
    owned = False
    if settings is not None:
        try:
            owned = _has_owned_hook(settings)
            if _remove_hook(settings):
                if settings:
                    _write_settings(settings_path, settings)
                else:
                    os.unlink(settings_path)
                    _remove_empty_parents(os.path.dirname(settings_path), root)
                removed.append(SETTINGS_RELATIVE)
        except (OSError, ValueError) as exc:
            warning = "settings.json could not be updated: %s" % exc
    elif os.path.lexists(settings_path):
        warning = "settings.json is %s; left untouched" % state

    script_state = _file_state(script_path, source_text())
    if script_state == "current" or owned:
        try:
            os.unlink(script_path)
            removed.append(SCRIPT_RELATIVE)
            _remove_empty_parents(os.path.dirname(script_path), root)
        except OSError as exc:
            raise CliError("could not remove SessionStart hook: %s" % exc)
    return RemoveResult(tuple(removed), warning)
