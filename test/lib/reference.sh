# test/lib/reference.sh — acquire the frozen Bash reference.
#
# The migration (issue #48) treats commit 9406cce as a fixed behavioural
# reference. This helper materialises it WITHOUT leaving a second long-lived
# copy in the working tree: it reads the file straight out of git history into
# a caller-owned temporary directory and marks it executable.
#
# Usage:
#   WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
#   . test/lib/reference.sh
#   aci_acquire_reference "$WORK"      # sets $ACI_REFERENCE
#
# Override the commit with ACI_REFERENCE_COMMIT (differential proofs after the
# 4.1.0 release may want a different pin).

ACI_REFERENCE_COMMIT="${ACI_REFERENCE_COMMIT:-9406cce}"

# aci_acquire_reference <work-dir> — writes <work-dir>/reference/agent-code-intel
# and exports its path as $ACI_REFERENCE.
aci_acquire_reference() {
  local work="$1" repo dest
  [[ -n "$work" && -d "$work" ]] || { echo "[ERROR: aci_acquire_reference needs an existing work directory]" >&2; return 1; }

  repo="$(git -C "$(dirname -- "${BASH_SOURCE[0]}")" rev-parse --show-toplevel 2>/dev/null)" \
    || { echo "[ERROR: reference acquisition must run inside the agent-code-intel git checkout]" >&2; return 1; }

  dest="$work/reference/agent-code-intel"
  mkdir -p "$work/reference"
  git -C "$repo" show "$ACI_REFERENCE_COMMIT:agent-code-intel" > "$dest" \
    || { echo "[ERROR: cannot read agent-code-intel from commit $ACI_REFERENCE_COMMIT]" >&2; return 1; }
  [[ -s "$dest" ]] || { echo "[ERROR: reference from $ACI_REFERENCE_COMMIT is empty]" >&2; return 1; }
  chmod +x "$dest"

  ACI_REFERENCE="$dest"
}
