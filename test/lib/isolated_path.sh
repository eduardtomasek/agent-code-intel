# test/lib/isolated_path.sh — build the isolated PATH the migration tests use.
#
# The reference suite (test/run.sh) runs hermetically under PATH=/usr/bin:/bin.
# On this machine /usr/bin/python3 is 3.9.6, but the 4.0.0 launcher's runtime
# gate rejects anything below 3.11 (issue #35, deviation 1). Running the suite
# against the Python launcher under the bare PATH would fail every test on the
# version banner instead of on behaviour.
#
# The fix decided in issue #43 §3: prepend a directory that contains ONLY a
# `python3` symlink to Python 3.11.x. GrepAI, GitNexus, Ollama, Node, Claude and
# Codex stay absent — the hermeticity that is the whole point of the bare PATH
# is preserved.
#
# 3.11 is the CONTRACT version (issue #48, testing decision 4): the mandatory
# suite runs under 3.11.x, newer minors are supplementary evidence only. So the
# default demands 3.11.x and errors if it is absent — it never silently drops to
# 3.12+. Use ACI_PYTHON to point at a specific interpreter for a supplementary
# run (3.13/3.14) or the 3.9.6 rejection check.
#
# Usage:
#   WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
#   . test/lib/isolated_path.sh
#   ISOLATED_PATH="$(aci_isolated_path "$WORK")"

ACI_CONTRACT_PYTHON="${ACI_CONTRACT_PYTHON:-3.11}"

# aci_find_python — echo the absolute path of the interpreter to use.
#   ACI_PYTHON set   -> exactly that, if it exists (no version constraint;
#                       the caller is asking for a specific supplementary run)
#   otherwise        -> a $ACI_CONTRACT_PYTHON.x interpreter, or nothing
aci_find_python() {
  local major minor cand
  major="${ACI_CONTRACT_PYTHON%%.*}"
  minor="${ACI_CONTRACT_PYTHON#*.}"

  if [[ -n "${ACI_PYTHON:-}" ]]; then
    command -v "$ACI_PYTHON" >/dev/null 2>&1 || return 1
    command -v "$ACI_PYTHON"
    return 0
  fi

  for cand in "python${ACI_CONTRACT_PYTHON}" python3 python; do
    command -v "$cand" >/dev/null 2>&1 || continue
    "$cand" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == ($major, $minor) else 1)" \
      >/dev/null 2>&1 || continue
    command -v "$cand"
    return 0
  done
  return 1
}

# aci_isolated_path <work-dir> — echo "<pybin>:/usr/bin:/bin", where <pybin> is
# a fresh directory under <work-dir> holding only a python3 symlink. Returns
# non-zero on failure (it runs inside a command substitution, so it must not
# exit); the caller checks with `if ! ISOLATED_PATH="$(aci_isolated_path …)"`.
aci_isolated_path() {
  local work="$1" py pybin
  [[ -n "$work" && -d "$work" ]] || { echo "[ERROR: aci_isolated_path needs an existing work directory]" >&2; return 1; }

  py="$(aci_find_python)" || {
    if [[ -n "${ACI_PYTHON:-}" ]]; then
      echo "[ERROR: ACI_PYTHON='$ACI_PYTHON' not found on PATH]" >&2
    else
      echo "[ERROR: no Python ${ACI_CONTRACT_PYTHON}.x found — the mandatory migration suite runs under the contract version (issue #48). Set ACI_PYTHON to run a supplementary check on another version.]" >&2
    fi
    return 1
  }

  pybin="$work/pybin"
  mkdir -p "$pybin"
  ln -sf "$py" "$pybin/python3"
  printf '%s\n' "$pybin:/usr/bin:/bin"
}
