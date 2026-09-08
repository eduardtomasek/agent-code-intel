# test/lib/isolated_path.sh — build the isolated PATH the migration tests use.
#
# The reference suite (test/run.sh) runs hermetically under PATH=/usr/bin:/bin.
# On this machine /usr/bin/python3 is 3.9.6, but the 4.0.0 launcher's runtime
# gate rejects anything below 3.11 (issue #35, deviation 1). Running the suite
# against the Python launcher under the bare PATH would fail every test on the
# version banner instead of on behaviour.
#
# The fix decided in issue #43 §3: prepend a directory that contains ONLY a
# `python3` symlink to an available Python >= 3.11. GrepAI, GitNexus, Ollama,
# Node, Claude and Codex stay absent — the hermeticity that is the whole point
# of the bare PATH is preserved.
#
# Usage:
#   WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
#   . test/lib/isolated_path.sh
#   ISOLATED_PATH="$(aci_isolated_path "$WORK")"

ACI_MIN_PYTHON="${ACI_MIN_PYTHON:-3.11}"

# aci_find_python — echo the absolute path of a python >= $ACI_MIN_PYTHON.
#
# ACI_PYTHON forces a specific interpreter (used for the supplementary 3.13/3.14
# runs, and for the 3.9.6 rejection check in a later slice). Otherwise the
# lowest matching minor wins: 3.11 is the contract version (issue #48, testing
# decision 4), newer ones are supplementary evidence, not the mandatory lane.
aci_find_python() {
  local want_major want_minor cand resolved
  want_major="${ACI_MIN_PYTHON%%.*}"
  want_minor="${ACI_MIN_PYTHON#*.}"

  if [[ -n "${ACI_PYTHON:-}" ]]; then
    command -v "$ACI_PYTHON" >/dev/null 2>&1 || return 1
    command -v "$ACI_PYTHON"
    return 0
  fi

  for cand in python3.11 python3.12 python3.13 python3.14 python3; do
    command -v "$cand" >/dev/null 2>&1 || continue
    "$cand" -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= ($want_major, $want_minor) else 1)" \
      >/dev/null 2>&1 || continue
    resolved="$(command -v "$cand")"
    printf '%s\n' "$resolved"
    return 0
  done
  return 1
}

# aci_isolated_path <work-dir> — echo "<pybin>:/usr/bin:/bin", where <pybin> is
# a fresh directory under <work-dir> holding only a python3 symlink.
aci_isolated_path() {
  local work="$1" py pybin
  [[ -n "$work" && -d "$work" ]] || { echo "[ERROR: aci_isolated_path needs an existing work directory]" >&2; exit 1; }

  py="$(aci_find_python)" \
    || { echo "[ERROR: no Python >= $ACI_MIN_PYTHON found — the migration reference suite requires it (issue #43)]" >&2; exit 1; }

  pybin="$work/pybin"
  mkdir -p "$pybin"
  ln -sf "$py" "$pybin/python3"
  printf '%s\n' "$pybin:/usr/bin:/bin"
}
