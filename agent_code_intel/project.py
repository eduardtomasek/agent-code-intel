"""project — project identity and health probes.

Resolves the project a run acts on — explicit workspace, a valid ``.code-intel``,
or the sanitized basename (issue #48, decision 30; issue #36 §7) — into an
immutable :class:`ProjectContext`, never executing ``.code-intel`` as shell
(decision 31, issue #36 P7). It also carries the legacy ``refresh-intel.sh``
helpers the apply / preview slice (#55) needs to adopt a pristine legacy
workspace; the top-level resolution here deliberately does *not* consult them,
because the reference does not either — it resolves the basename slug and lets
``--apply`` override it (``9406cce`` :547–:569 vs :1350–:1367).

The status table and JSON status (issue #53) also read the project registry
here and the pure ``.grepai/config.yaml`` checks the status probes need; the
external-tool probes live in :mod:`agent_code_intel.integrations`.

Importing this module does no I/O (decision 43).
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
import re
import string
import subprocess

from .config import CliError


@dataclasses.dataclass(frozen=True)
class Identity:
    """The outcome of reading ``.code-intel`` (``9406cce`` :446–:512).

    ``status`` is ``"OK"`` / ``"ABSENT"`` / ``"ERR"``; ``message`` is set only
    for ``"ERR"`` and is the exact text ``die`` would print.
    """

    status: str
    workspace: str | None = None
    project: str | None = None
    message: str | None = None


@dataclasses.dataclass(frozen=True)
class ProjectContext:
    """The resolved project as one immutable value (issue #41 §3).

    ``ident_*`` echo what ``.code-intel`` said, so a later slice can tell an
    adopted identity from a derived one without re-reading the file.
    """

    root: str
    workspace: str
    proj_name: str
    grepai_cfg: str
    mcp_json: str
    refresh_script: str
    ident_status: str
    ident_workspace: str | None
    ident_project: str | None
    workspace_explicit: bool = False


_LINE_RE = re.compile(r"^[A-Z][A-Z0-9_]*=\S+$")
_KNOWN_KEYS = ("SCHEMA", "WORKSPACE", "PROJECT")
_SUPPORTED_SCHEMA = "1"
_LOWER = str.maketrans(string.ascii_uppercase, string.ascii_lowercase)
_STAMP_RE = re.compile(rb"^# code-intel-init: version=(\S+) body=([0-9a-f]{64})$")

# `.grepai/config.yaml` shape checks — pure file reads, the exact regexes the
# reference's `cfg_chunking_ok` / `cfg_ignores_ok` embedded (``9406cce``
# :653–:675). Not a YAML parser (decision: "Nepřidávat vlastní obecný YAML
# parser").
_CHUNKING_RE = re.compile(
    r"^chunking:\n[ \t]+size: (\d+)\n[ \t]+overlap: (\d+)$", re.M
)
_IGNORE_BLOCK_RE = re.compile(r"^ignore:\n((?:[ \t]+- .*\n?)*)", re.M)
_IGNORE_ITEM_RE = re.compile(r"^[ \t]+- (.*?)[ \t]*$", re.M)


def canon(path: str) -> str:
    """Canonical physical path of an existing directory (``9406cce`` :147–:155).

    Prefers the external ``/bin/pwd -P`` (goes through ``getcwd()`` and returns
    the on-disk casing on a case-insensitive volume); falls back to the shell
    builtin's equivalent, and returns the input unchanged for a non-directory
    or if the ``cd`` fails (TOL-7).
    """

    if not os.path.isdir(path):
        return path
    pwd = "/bin/pwd" if os.path.isfile("/bin/pwd") else "pwd"
    try:
        result = subprocess.run(
            [pwd, "-P"], cwd=path, capture_output=True, text=True
        )
    except OSError:
        return path
    if result.returncode != 0:
        return path
    return result.stdout.rstrip("\n")


def read_code_intel(root: str) -> Identity:
    """Port of the embedded ``.code-intel`` parser (``9406cce`` :463–:512).

    Never raises and never executes the file: three text outcomes for the
    caller, which itself decides whether ``ERR`` is fatal.
    """

    path = os.path.join(root, ".code-intel")
    if not os.path.isfile(path):
        return Identity("ABSENT")

    base = os.path.basename(root)
    values: dict[str, str] = {}
    with open(path, encoding="utf-8", errors="replace") as handle:
        for lineno, raw in enumerate(handle, 1):
            line = raw.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            if not _LINE_RE.match(line):
                return _err("%s:%d: malformed line: %r" % (path, lineno, line))
            key, val = line.split("=", 1)
            if key not in _KNOWN_KEYS:
                return _err("%s:%d: unknown key '%s'" % (path, lineno, key))
            if key in values:
                return _err("%s:%d: duplicate key '%s'" % (path, lineno, key))
            values[key] = val

    for key in _KNOWN_KEYS:
        if key not in values:
            return _err("%s: missing required key %s" % (path, key))

    if values["SCHEMA"] != _SUPPORTED_SCHEMA:
        return _err(
            "%s: unsupported SCHEMA=%s (this tool understands %s)"
            % (path, values["SCHEMA"], _SUPPORTED_SCHEMA)
        )

    if values["PROJECT"] != base:
        return _err(
            "%s: says PROJECT=%s, but this directory is named '%s' -- "
            "rename the directory back, or fix PROJECT in %s"
            % (path, values["PROJECT"], base, path)
        )

    return Identity("OK", workspace=values["WORKSPACE"], project=values["PROJECT"])


def read_registry(path: str) -> list[tuple[str, str]]:
    """The tool's own project registry: ``<workspace>\\t<path>`` per line
    (``9406cce`` :123, :1952). A line with an empty workspace or path, or no
    tab, is skipped — the reference's ``[[ -n "$w" && -n "$p" ]] || continue``.
    A missing file is an empty registry, never an error.
    """

    try:
        with open(path, encoding="utf-8", errors="surrogateescape") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return []
    rows: list[tuple[str, str]] = []
    for line in lines:
        if "\t" not in line:
            continue
        workspace, project_path = line.split("\t", 1)
        if not workspace or not project_path:
            continue
        rows.append((workspace, project_path))
    return rows


def grepai_config_chunking_ok(
    config_path: str, chunk_size: str, chunk_overlap: str
) -> bool:
    """``.grepai/config.yaml`` declares exactly this chunk size and overlap
    (``9406cce`` :653). A missing or unreadable file is ``False``."""

    text = _read_text(config_path)
    if text is None:
        return False
    match = _CHUNKING_RE.search(text)
    return bool(match) and match.group(1) == chunk_size and match.group(2) == chunk_overlap


def grepai_config_ignores_ok(config_path: str, extra_ignores: tuple[str, ...]) -> bool:
    """Every configured ignore entry is present in ``.grepai/config.yaml``'s
    ``ignore:`` block (``9406cce`` :664). A missing or unreadable file, or a
    missing block, is ``False``."""

    text = _read_text(config_path)
    if text is None:
        return False
    block = _IGNORE_BLOCK_RE.search(text)
    if not block:
        return False
    present = set(_IGNORE_ITEM_RE.findall(block.group(1)))
    return all(entry in present for entry in extra_ignores)


def update_grepai_config(
    config_path: str,
    chunk_size: str,
    chunk_overlap: str,
    extra_ignores: tuple[str, ...],
) -> tuple[str, bool]:
    """Update only the owned chunking and ignore-list portions of GrepAI YAML.

    This intentionally uses the same narrow regex transforms as the Bash
    reference; it is not a general YAML parser and leaves all other content
    untouched.
    """

    try:
        with open(config_path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return "", False

    before = text
    chunk = _CHUNKING_RE.search(text)
    if not chunk:
        raise ValueError(".grepai/config.yaml is missing its chunking block")
    if chunk and (chunk.group(1) != chunk_size or chunk.group(2) != chunk_overlap):
        indent = re.search(r"^chunking:\n(?P<i>[ \t]+)", chunk.group(0), re.M)
        spacing = indent.group("i") if indent else "  "
        replacement = "chunking:\n%ssize: %s\n%soverlap: %s" % (
            spacing,
            chunk_size,
            spacing,
            chunk_overlap,
        )
        text = text[: chunk.start()] + replacement + text[chunk.end() :]

    block = _IGNORE_BLOCK_RE.search(text)
    if extra_ignores and not block:
        raise ValueError(".grepai/config.yaml is missing its ignore block")
    if block and extra_ignores:
        items = block.group(1)
        present = set(_IGNORE_ITEM_RE.findall(items))
        missing = [entry for entry in extra_ignores if entry not in present]
        if missing:
            first_indent = re.search(r"^[ \t]+", items, re.M)
            spacing = first_indent.group(0) if first_indent else "    "
            if items and not items.endswith("\n"):
                items += "\n"
            items += "".join("%s- %s\n" % (spacing, entry) for entry in missing)
            text = text[: block.start(1)] + items + text[block.end(1) :]

    return text, text != before


def doc_state(path: str) -> str:
    """Return ``missing``, ``present`` or ``orphaned`` for owned markers."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        return "missing"
    starts = text.count("<!-- code-intel:start -->")
    ends = text.count("<!-- code-intel:end -->")
    if starts == 0 and ends == 0:
        return "missing"
    return "present" if starts == 1 and ends == 1 else "orphaned"


def managed_doc_current(path: str, block: str) -> bool:
    """Whether the one balanced managed block already has canonical bytes."""
    if doc_state(path) != "present":
        return False
    text = _read_text(path)
    if text is None:
        return False
    match = re.search(
        r"<!-- code-intel:start -->.*?<!-- code-intel:end -->", text, flags=re.S
    )
    return match is not None and match.group(0) == block


def project_has_sources(root: str) -> bool:
    """True when the project contains files worth indexing."""
    excluded_dirs = {".git", ".grepai", ".gitnexus", "node_modules", ".venv", "venv"}
    excluded_files = {
        ".gitignore",
        "CLAUDE.md",
        "AGENTS.md",
        "refresh-intel.sh",
        ".mcp.json",
        ".DS_Store",
    }
    for current, dirs, files in os.walk(root):
        dirs[:] = [name for name in dirs if name not in excluded_dirs]
        if any(name not in excluded_files for name in files):
            return True
    return False


def gitignore_ok(path: str, entries: tuple[str, ...]) -> bool:
    """Whether every configured ignore entry exists as a complete line."""
    try:
        with open(path, encoding="utf-8") as handle:
            lines = {line.rstrip("\n") for line in handle}
    except OSError:
        return False
    return all(entry in lines for entry in entries)


def code_intel_present(context: ProjectContext) -> bool:
    """Whether the already-read identity exactly matches this run."""
    return (
        context.ident_status == "OK"
        and context.ident_workspace == context.workspace
        and context.ident_project == context.proj_name
    )


def registry_add(path: str, workspace: str, project_path: str) -> None:
    """Replace the registry entry for a path and append its current mapping."""
    try:
        with open(path, encoding="utf-8", errors="surrogateescape") as handle:
            rows = [line for line in handle.read().splitlines() if "\t" not in line or line.split("\t", 1)[1] != project_path]
    except OSError:
        rows = []
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rows.append("%s\t%s" % (workspace, project_path))
    with open(path, "w", encoding="utf-8", errors="surrogateescape") as handle:
        handle.write("\n".join(rows) + "\n")


def registry_delete(path: str, project_path: str) -> None:
    """Remove the registry row for ``project_path`` without treating it as a regex."""
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8", errors="surrogateescape") as handle:
        rows = [
            line
            for line in handle.read().splitlines()
            if "\t" not in line or line.split("\t", 1)[1] != project_path
        ]
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8", errors="surrogateescape") as handle:
        if rows:
            handle.write("\n".join(rows) + "\n")
    os.replace(temporary, path)


def remove_managed_doc(path: str) -> str | None:
    """Remove one owned code-intel block, returning ``stripped`` or ``removed``.

    Unbalanced markers are protected and return ``None``. The caller owns the
    user-facing wording and decides whether the operation is part of a plan.
    """
    if doc_state(path) != "present":
        return None
    with open(path, encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    updated = re.sub(
        r"\n*<!-- code-intel:start -->.*?<!-- code-intel:end -->\n*",
        "\n",
        text,
        count=1,
        flags=re.S,
    )
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(updated)
    if not updated.strip():
        os.unlink(path)
        return "removed"
    return "stripped"


def write_managed_doc(path: str, block: str, force: bool) -> tuple[str, bool]:
    """Write or replace only the code-intel block in a documentation file."""
    state = doc_state(path)
    if state == "orphaned":
        return "unbalanced code-intel markers — fix them by hand, left untouched", False
    if state == "present" and managed_doc_current(path, block):
        return "code-intel block already present", False
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        text = ""
    if state == "present":
        updated = re.sub(
            r"<!-- code-intel:start -->.*?<!-- code-intel:end -->",
            block,
            text,
            count=1,
            flags=re.S,
        )
    else:
        updated = text
        if updated and not updated.endswith("\n"):
            updated += "\n"
        if updated:
            updated += "\n"
        updated += block + "\n"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(updated)
    return ("code-intel block rewritten in place" if state == "present" else "code-intel block written"), True


def _read_text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return None


def slug(name: str) -> str:
    """The workspace slug from a directory basename (``9406cce`` :563).

    ``tr '[:upper:]' '[:lower:]'`` then
    ``sed 's/[^a-z0-9-]/-/g; s/--*/-/g; s/^-//; s/-$//'``. Lower-casing is
    ASCII-only, matching ``tr`` under the tests' C locale.
    """

    lowered = name.translate(_LOWER)
    dashed = re.sub(r"[^a-z0-9-]", "-", lowered)
    collapsed = re.sub(r"-+", "-", dashed)
    return collapsed.strip("-")


def legacy_refresh_is_pristine(path: str) -> bool:
    """True if ``refresh-intel.sh`` carries a stamp whose sha256 matches its
    body — an untouched, tool-generated script (``9406cce`` :757–:768)."""

    try:
        with open(path, "rb") as handle:
            lines = handle.read().split(b"\n")
    except OSError:
        return False
    for i, line in enumerate(lines):
        match = _STAMP_RE.match(line)
        if match:
            body = b"\n".join(lines[:i] + lines[i + 1 :])
            return hashlib.sha256(body).hexdigest() == match.group(2).decode()
    return False


def read_legacy_workspace(path: str) -> str:
    """The ``WORKSPACE="…"`` line from a legacy script, or ``""``
    (``9406cce`` :774–:780). Bare read: the caller has already confirmed the
    script is pristine."""

    try:
        with open(path) as handle:
            text = handle.read()
    except OSError:
        return ""
    match = re.search(r'^WORKSPACE="([^"]*)"$', text, re.M)
    return match.group(1) if match else ""


def adopt_legacy_workspace(
    workspace: str | None,
    workspace_explicit: bool,
    legacy_workspace: str,
    refresh_script: str,
) -> str:
    """Resolve the workspace when a pristine legacy script is present
    (``9406cce`` :788–:796). An explicit CLI workspace still wins, and a
    conflict between the two is a hard error, never resolved silently."""

    if not legacy_workspace:
        raise CliError(
            "%s passed the pristine check but has no WORKSPACE= line -- "
            "internal error, please report" % refresh_script
        )
    if workspace_explicit and workspace != legacy_workspace:
        raise CliError(
            "explicit workspace '%s' conflicts with '%s' read from %s"
            % (workspace, legacy_workspace, refresh_script)
        )
    return legacy_workspace


def resolve_project(
    *,
    root: str,
    root_explicit: bool,
    mode: str,
    workspace: str | None,
    home: str,
    status_all: bool,
) -> ProjectContext:
    """Reproduce the reference's path + identity resolution
    (``9406cce`` :514–:572).

    ``--refresh`` without ``--path`` resolves to the nearest git root and never
    founds a project; the home / fs-root guards are skipped only for
    ``--status --all``; ``.code-intel`` outranks the basename derivation but an
    explicit workspace wins outright.
    """

    if mode == "refresh" and not root_explicit:
        toplevel = _git_toplevel(root)
        if toplevel is None:
            raise CliError(
                "not inside a git repository: %s — pass --path, or run "
                "--apply in a git repo first" % root
            )
        root = toplevel

    if not os.path.isdir(root):
        raise CliError("not a directory: %s" % root)

    root = canon(root)

    if not (mode == "status" and status_all):
        home_real = canon(home)
        if root == home_real:
            raise CliError(
                "refusing to run over your home directory (%s) — point --path "
                "at a single project" % root
            )
        if root == "/":
            raise CliError("refusing to run over the filesystem root")
        if home_real.startswith(root + "/"):
            raise CliError(
                "refusing to run over %s: it contains your home directory (%s)"
                % (root, home_real)
            )

    identity = read_code_intel(root)
    workspace_was_explicit = workspace is not None
    ws = workspace

    if identity.status == "ERR":
        raise CliError(identity.message or "")
    elif identity.status == "OK":
        if not ws:
            ws = identity.workspace
        proj = identity.project
    else:  # ABSENT
        if mode == "refresh":
            raise CliError(
                "no .code-intel in %s — this project has not been set up; "
                "run: agent-code-intel --path %s --apply" % (root, root)
            )
        if not ws:
            ws = slug(os.path.basename(root))
        proj = os.path.basename(root)

    if not ws:
        raise CliError(
            "could not derive a workspace name from %s; pass one explicitly" % root
        )

    return ProjectContext(
        root=root,
        workspace=ws,
        proj_name=proj,
        grepai_cfg=os.path.join(root, ".grepai", "config.yaml"),
        mcp_json=os.path.join(root, ".mcp.json"),
        refresh_script=os.path.join(root, "refresh-intel.sh"),
        ident_status=identity.status,
        ident_workspace=identity.workspace,
        ident_project=identity.project,
        workspace_explicit=workspace_was_explicit,
    )


def _err(message: str) -> Identity:
    return Identity("ERR", message=message)


def _git_toplevel(start: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", start, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None
