# scenario: `--status --json` over a registered project with no stack running.
# Read-only: exit 0, machine JSON on stdout, nothing written anywhere.
# Exercises the structural-JSON comparison, meta.generated_at normalization,
# and the file manifest (asserting the read-only contract).

scenario_name()       { echo "status-json-drift"; }
scenario_invariants() { echo "ID-1 JSON-1 JSON-2 JSON-3 JSON-5"; }
scenario_args()       { echo "--status --json"; }

scenario_setup() {
  local fixture="$1" home="$2"
  ( cd "$fixture"
    git init -q .
    printf 'x\n' > file.txt
    printf 'SCHEMA=1\nWORKSPACE=diff-json-ws\nPROJECT=%s\n' "$(basename "$fixture")" > .code-intel )
  mkdir -p "$home/.config/code-intel"
  printf 'diff-json-ws\t%s\n' "$fixture" > "$home/.config/code-intel/projects"
}
