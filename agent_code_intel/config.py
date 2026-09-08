"""config — user configuration and the child environment.

Owns the built-in defaults, loading ``defaults.toml`` (via :mod:`tomllib`) and
executing the legacy ``defaults.env`` as real bash, deciding which of the four
existence states applies, and turning the result into an immutable ``Config``
plus an immutable ``ChildEnvironment`` that every subprocess inherits
(issue #48, decisions 14–28, 36; issues #36–#38, #41 §4).

This module sits at the bottom of the dependency graph — it imports nothing
from :mod:`agent_code_intel` above it (decision 34). :class:`CliError` lives
here, not in :mod:`agent_code_intel.cli`, precisely so ``config`` and
``project`` can raise it without importing a module above them.

Importing this module does no I/O and reads no file (decision 43); the loader
only touches the filesystem when :func:`load` is called from ``cli.main``.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
import subprocess
import tempfile
import tomllib
from collections.abc import Mapping
from typing import Sequence, TextIO


class CliError(Exception):
    """A deliberate, user-facing failure — one of exactly three error paths
    (issue #48, decision 41; issue #41 §7).

    ``wrap`` (the default) renders it as the reference's ``die``:
    ``[ERROR: <msg>]`` on stderr, exit 1. ``wrap=False`` writes ``<msg>``
    verbatim and exits ``code`` — the faithful port of ``defaults.env``'s
    silent death under ``set -e`` (issue #38 §2.11): bash's own stderr passes
    straight through and this tool adds nothing.
    """

    def __init__(self, message: str = "", *, code: int = 1, wrap: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.wrap = wrap


# ------------------------------------------------------------------ schema --
#
# The flat 13-key contract (issue #37 §3). Key = the ``defaults.env`` variable
# lower-cased; no sections. Four keys are integers in TOML but "numbers as
# strings" in bash — they flow into argv, URLs and .grepai/config.yaml and
# cfg_chunking_ok compares them as text — so Config stores every scalar as a
# string and both arrays as tuples, which makes the ENV and TOML paths produce
# identical values (issue #37 §3, decision 16).

_SCALAR_KEYS: tuple[str, ...] = (
    "qdrant_host",
    "qdrant_http_port",
    "qdrant_port",
    "qdrant_container",
    "qdrant_image",
    "qdrant_volume",
    "ollama_http",
    "embed_provider",
    "embed_model",
    "chunk_size",
    "chunk_overlap",
)
_INT_KEYS: frozenset[str] = frozenset(
    {"qdrant_http_port", "qdrant_port", "chunk_size", "chunk_overlap"}
)
_ARRAY_KEYS: tuple[str, ...] = ("extra_ignores", "gitignore_entries")
_ALL_KEYS: frozenset[str] = frozenset(_SCALAR_KEYS + _ARRAY_KEYS)

# Built-in defaults — character-for-character the reference's assignments
# (``9406cce`` lines 94–119). This is the single source; the bash harvester's
# presets are generated from it below.
_DEFAULT_SCALARS: dict[str, str] = {
    "qdrant_host": "127.0.0.1",
    "qdrant_http_port": "6333",
    "qdrant_port": "6334",
    "qdrant_container": "grepai-qdrant",
    "qdrant_image": "qdrant/qdrant",
    "qdrant_volume": "grepai-qdrant-data",
    "ollama_http": "http://localhost:11434",
    "embed_provider": "ollama",
    "embed_model": "nomic-embed-text-v2-moe",
    "chunk_size": "256",
    "chunk_overlap": "25",
}
_DEFAULT_EXTRA_IGNORES: tuple[str, ...] = (
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lockb",
    "go.sum",
    "Cargo.lock",
    "composer.lock",
    "poetry.lock",
    "uv.lock",
    "Gemfile.lock",
    ".claude",
    ".mcp.json",
)
_DEFAULT_GITIGNORE_ENTRIES: tuple[str, ...] = (".grepai/", ".gitnexus/")

# The 16 names the bash harvester presets and transfers back (issue #38 §2.2,
# §3): 11 scalars + 2 arrays + the three config paths, minus VERSION.
_ENV_SCALAR_NAMES: dict[str, str] = {
    "QDRANT_HOST": "qdrant_host",
    "QDRANT_HTTP_PORT": "qdrant_http_port",
    "QDRANT_PORT": "qdrant_port",
    "QDRANT_CONTAINER": "qdrant_container",
    "QDRANT_IMAGE": "qdrant_image",
    "QDRANT_VOLUME": "qdrant_volume",
    "OLLAMA_HTTP": "ollama_http",
    "EMBED_PROVIDER": "embed_provider",
    "EMBED_MODEL": "embed_model",
    "CHUNK_SIZE": "chunk_size",
    "CHUNK_OVERLAP": "chunk_overlap",
}
_ENV_ARRAY_NAMES: dict[str, str] = {
    "EXTRA_IGNORES": "extra_ignores",
    "GITIGNORE_ENTRIES": "gitignore_entries",
}
_ENV_PATH_NAMES: tuple[str, ...] = ("CONF_DIR", "CONF_FILE", "REGISTRY")


@dataclasses.dataclass(frozen=True)
class Config:
    """The resolved tuning values as one immutable value (issue #41 §4).

    Every scalar is a string and both collections are tuples — the exact shape
    the bash reference exposes, so an ENV run and an equivalent TOML run yield
    the same ``Config``.
    """

    qdrant_host: str
    qdrant_http_port: str
    qdrant_port: str
    qdrant_container: str
    qdrant_image: str
    qdrant_volume: str
    ollama_http: str
    embed_provider: str
    embed_model: str
    chunk_size: str
    chunk_overlap: str
    extra_ignores: tuple[str, ...]
    gitignore_entries: tuple[str, ...]


class ChildEnvironment(Mapping):
    """The immutable environment every subprocess inherits (issue #41 §4).

    Built from a full copy of the parent environment plus whatever
    ``defaults.env`` exported; the global ``os.environ`` is never mutated
    (issue #38 §2.8, decision 26). Read-only: it is a :class:`Mapping` with no
    mutators.
    """

    __slots__ = ("_data",)

    def __init__(self, data: Mapping[str, str]) -> None:
        self._data = dict(data)

    def __getitem__(self, key: str) -> str:
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def as_dict(self) -> dict[str, str]:
        return dict(self._data)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return "ChildEnvironment(%d names)" % len(self._data)


@dataclasses.dataclass(frozen=True)
class LoadedConfig:
    """What :func:`load` returns: the tuning values, the child environment, and
    the config path ``meta.config_file`` should report — the file actually
    read, or the ``defaults.toml`` path when neither file exists (issue #37 §7,
    DEV/CFG-1).

    ``conf_paths`` carries the post-source ``CONF_DIR`` / ``CONF_FILE`` /
    ``REGISTRY`` values (issue #38 §2.3); the modes that need them land later.
    """

    config: Config
    child_env: ChildEnvironment
    config_file: str
    source: str  # "toml" | "env" | "defaults"
    conf_paths: Mapping[str, str] = dataclasses.field(default_factory=dict)


def default_config() -> Config:
    """The built-in defaults, no file involved (issue #37 §6: no config → defaults)."""
    return _config_from(
        dict(_DEFAULT_SCALARS),
        _DEFAULT_EXTRA_IGNORES,
        _DEFAULT_GITIGNORE_ENTRIES,
    )


def load(
    conf_dir: str,
    environ: Mapping[str, str],
    cwd: str,
    stderr: TextIO,
) -> LoadedConfig:
    """Resolve configuration for a run.

    The four existence states (issue #37 §6, decision 22):

    * both ``defaults.env`` and ``defaults.toml`` → hard error *before either
      is read* (issue #37 §8, issue #38 preamble);
    * only ``defaults.toml`` → parsed via :mod:`tomllib`;
    * only ``defaults.env`` → executed as real bash in ``cwd``;
    * neither → built-in defaults.

    Raises :class:`CliError` on a conflict, a TOML error, missing ``bash``, or
    an ``unset`` transferred name; writes bash's own stderr through and raises
    ``CliError(wrap=False)`` when the sourced file dies (issue #38 §2.11).
    """

    env_path = os.path.join(conf_dir, "defaults.env")
    toml_path = os.path.join(conf_dir, "defaults.toml")
    env_exists = os.path.isfile(env_path)
    toml_exists = os.path.isfile(toml_path)

    if env_exists and toml_exists:
        raise CliError(
            "%s: both defaults.env and defaults.toml exist; keep one" % conf_dir
        )

    if toml_exists:
        return LoadedConfig(
            config=_load_toml(toml_path),
            child_env=ChildEnvironment(environ),
            config_file=toml_path,
            source="toml",
        )

    if env_exists:
        config, child_env, conf_paths = _load_env(env_path, environ, cwd, stderr)
        return LoadedConfig(
            config=config,
            child_env=child_env,
            config_file=env_path,
            source="env",
            conf_paths=conf_paths,
        )

    return LoadedConfig(
        config=default_config(),
        child_env=ChildEnvironment(environ),
        config_file=toml_path,
        source="defaults",
    )


# ---------------------------------------------------------------- helpers --


def _config_from(
    scalars: Mapping[str, str],
    extra_ignores: Sequence[str],
    gitignore_entries: Sequence[str],
) -> Config:
    return Config(
        extra_ignores=tuple(extra_ignores),
        gitignore_entries=tuple(gitignore_entries),
        **{k: scalars[k] for k in _SCALAR_KEYS},
    )


def _typename(value: object) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "table"
    return type(value).__name__


def _load_toml(path: str) -> Config:
    """Parse ``defaults.toml``: unknown key, wrong type and unparsable TOML are
    hard errors; a well-typed but out-of-range value is *not* checked, because
    that would reject configuration the ENV path accepts (issue #37 §5)."""

    try:
        with open(path, "rb") as handle:
            raw = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise CliError("%s: %s" % (path, exc))
    except OSError as exc:  # pragma: no cover - isfile() just said it exists
        raise CliError("%s: %s" % (path, exc))

    scalars = dict(_DEFAULT_SCALARS)
    extra_ignores: tuple[str, ...] = _DEFAULT_EXTRA_IGNORES
    gitignore_entries: tuple[str, ...] = _DEFAULT_GITIGNORE_ENTRIES

    for key, value in raw.items():
        if key not in _ALL_KEYS:
            raise CliError("%s: unknown key '%s'" % (path, key))

        if key in _INT_KEYS:
            if isinstance(value, bool) or not isinstance(value, int):
                raise CliError(
                    "%s: key '%s' must be an integer, got %s"
                    % (path, key, _typename(value))
                )
            scalars[key] = str(value)
        elif key in _SCALAR_KEYS:
            if not isinstance(value, str):
                raise CliError(
                    "%s: key '%s' must be a string, got %s"
                    % (path, key, _typename(value))
                )
            scalars[key] = value
        else:  # an array key
            if not isinstance(value, list) or not all(
                isinstance(item, str) for item in value
            ):
                raise CliError(
                    "%s: key '%s' must be an array of strings, got %s"
                    % (path, key, _typename(value))
                )
            if key == "extra_ignores":
                extra_ignores = tuple(value)
            else:
                gitignore_entries = tuple(value)

    return _config_from(scalars, extra_ignores, gitignore_entries)


# The bash harvester (issue #38 §3). Presets all 16 declared names to the
# built-in defaults — a defaults.env that references $QDRANT_HOST dies on
# `set -u` without this (E7) — sources the user's file in their cwd, then
# writes a NUL-delimited frame for the 16 names plus a NUL-delimited env dump
# for the export delta. `set -e` is kept so a non-zero command in the sourced
# file still kills the run silently, exactly as today (E2, §2.11). The frame
# code is static per-name (no `eval`, no dynamic variable names): `${V+x}`
# distinguishes an unset scalar, `declare -p` an unset array from an empty one
# (E16/E17), and `"$V"` / `"${V[@]}"` give bash's own scalar-vs-array coercion
# for a slot mismatch (E8).
def _sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def _harvest_script() -> str:
    out: list[str] = ["set -euo pipefail", "", '_frame="$1"; _envdump="$2"; _conf="$3"', ""]

    for name, key in _ENV_SCALAR_NAMES.items():
        out.append("%s=%s" % (name, _sh_quote(_DEFAULT_SCALARS[key])))
    out.append(
        "EXTRA_IGNORES=(%s)" % " ".join(_sh_quote(x) for x in _DEFAULT_EXTRA_IGNORES)
    )
    out.append(
        "GITIGNORE_ENTRIES=(%s)"
        % " ".join(_sh_quote(x) for x in _DEFAULT_GITIGNORE_ENTRIES)
    )
    out += [
        '_dir=$(dirname "$_conf")',
        'CONF_DIR="$_dir"',
        'CONF_FILE="$_conf"',
        'REGISTRY="$_dir/projects"',
        "",
        '. "$_conf"',
        "",
        "{",
    ]

    for name in list(_ENV_SCALAR_NAMES) + list(_ENV_PATH_NAMES):
        q = _sh_quote(name)
        out += [
            '  if [ -z "${%s+x}" ]; then' % name,
            "    printf '%%s\\0unset\\0' %s" % q,
            "  else",
            "    printf '%%s\\0scalar\\0%%s\\0' %s \"$%s\"" % (q, name),
            "  fi",
        ]

    for name in _ENV_ARRAY_NAMES:
        q = _sh_quote(name)
        out += [
            "  if declare -p %s >/dev/null 2>&1; then" % name,
            "    printf '%%s\\0array\\0%%s\\0' %s \"${#%s[@]}\"" % (q, name),
            '    for _x in ${%s+"${%s[@]}"}; do printf \'%%s\\0\' "$_x"; done'
            % (name, name),
            "  else",
            "    printf '%%s\\0unset\\0' %s" % q,
            "  fi",
        ]

    out += [
        '} > "$_frame"',
        'env -0 > "$_envdump" 2>/dev/null'
        ' || /usr/bin/env -0 > "$_envdump" 2>/dev/null || true',
    ]
    return "\n".join(out) + "\n"


def _load_env(
    env_path: str,
    environ: Mapping[str, str],
    cwd: str,
    stderr: TextIO,
) -> tuple[Config, ChildEnvironment, dict[str, str]]:
    # `bash` from PATH, matching the reference's `#!/usr/bin/env bash`, and only
    # when defaults.env exists (issue #38 §3, Q10).
    bash = shutil.which("bash", path=environ.get("PATH"))
    if bash is None:
        raise CliError("bash is required to load %s" % env_path)

    with tempfile.TemporaryDirectory(prefix="aci-env-") as scratch:
        frame_path = os.path.join(scratch, "frame")
        dump_path = os.path.join(scratch, "env")
        proc = subprocess.run(
            [bash, "-c", _harvest_script(), "bash", frame_path, dump_path, env_path],
            cwd=cwd,
            env=dict(environ),
            stdout=None,
            stderr=subprocess.PIPE,
            text=True,
        )

        if proc.returncode != 0 or not os.path.isfile(frame_path):
            # The sourced file died under `set -e` — pass bash's own stderr
            # through untouched and add nothing (issue #38 §2.11).
            raise CliError(proc.stderr, code=proc.returncode or 1, wrap=False)

        with open(frame_path, "rb") as handle:
            frame = _parse_frame(handle.read())
        child_env = _parse_env_dump(_read_bytes(dump_path), environ)

    scalars = dict(_DEFAULT_SCALARS)
    for name, key in _ENV_SCALAR_NAMES.items():
        scalars[key] = _scalar_value(env_path, name, frame[name])

    arrays: dict[str, tuple[str, ...]] = {}
    for name, key in _ENV_ARRAY_NAMES.items():
        arrays[key] = _array_value(env_path, name, frame[name])

    conf_paths = {
        name: _scalar_value(env_path, name, frame[name]) for name in _ENV_PATH_NAMES
    }

    config = _config_from(scalars, arrays["extra_ignores"], arrays["gitignore_entries"])
    return config, child_env, conf_paths


def _read_bytes(path: str) -> bytes:
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return b""


def _parse_frame(data: bytes) -> dict[str, tuple]:
    parts = data.split(b"\0")
    result: dict[str, tuple] = {}
    i = 0
    while i < len(parts):
        name = parts[i].decode("utf-8", "surrogateescape")
        if name == "" and i == len(parts) - 1:
            break
        kind = parts[i + 1].decode()
        if kind == "unset":
            result[name] = ("unset",)
            i += 2
        elif kind == "scalar":
            result[name] = ("scalar", parts[i + 2].decode("utf-8", "surrogateescape"))
            i += 3
        elif kind == "array":
            count = int(parts[i + 2].decode())
            items = [
                parts[i + 3 + j].decode("utf-8", "surrogateescape") for j in range(count)
            ]
            result[name] = ("array", tuple(items))
            i += 3 + count
        else:  # pragma: no cover - the harvester only emits the three kinds
            raise CliError("defaults.env harvester emitted an unknown frame kind %r" % kind)
    return result


def _parse_env_dump(data: bytes, environ: Mapping[str, str]) -> ChildEnvironment:
    merged = dict(environ)
    for entry in data.split(b"\0"):
        if not entry:
            continue
        text = entry.decode("utf-8", "surrogateescape")
        name, _, value = text.partition("=")
        merged[name] = value
    return ChildEnvironment(merged)


def _scalar_value(env_path: str, name: str, cell: tuple) -> str:
    kind = cell[0]
    if kind == "unset":
        raise CliError(
            "%s: configuration name '%s' was unset" % (env_path, name)
        )
    if kind == "scalar":
        return cell[1]
    # An array in a scalar slot: bash's "$V" takes the first element (E8).
    items = cell[1]
    return items[0] if items else ""


def _array_value(env_path: str, name: str, cell: tuple) -> tuple[str, ...]:
    kind = cell[0]
    if kind == "unset":
        raise CliError(
            "%s: configuration name '%s' was unset" % (env_path, name)
        )
    if kind == "array":
        # Empty array = valid empty list (issue #35 DEV-14, issue #38 §2.6).
        return cell[1]
    # A scalar in an array slot: a single-element list (E8).
    return (cell[1],)
