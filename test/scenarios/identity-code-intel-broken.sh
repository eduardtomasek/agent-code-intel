# scenario: a git repo with a `.code-intel` carrying an unknown key. Both the
# Bash reference and the Python port parse the file strictly (never source it),
# hit the unknown key and die with the identical `path:line: unknown key '…'`
# text — top-level identity resolution runs before mode dispatch in both
# (`9406cce` :547 vs issue #41 §4). Zero divergence.

scenario_name()       { echo "identity-code-intel-broken"; }
scenario_invariants() { echo "ID-1 TOL-1"; }
scenario_args()       { echo ""; }

scenario_setup() {
  local fixture="$1"
  ( cd "$fixture"
    git init -q .
    printf 'x\n' > file.txt
    printf 'SCHEMA=1\nWORKSPACE=w\nPROJECT=%s\nBOGUS=1\n' "$(basename "$fixture")" \
      > .code-intel )
}
