# scenario: `--status --all` with an empty registry file. The reference prints
# `registry is empty (<path>)` and exits 0 (ID-8: exit 0 all-ok including the
# empty registry). Run from a set-up project so identity resolution succeeds
# before the mode runs.

scenario_name()       { echo "status-all-empty"; }
scenario_invariants() { echo "ID-8"; }
scenario_args()       { echo "--status --all"; }

scenario_setup() {
  local fixture="$1" home="$2" tag="$3"
  ( cd "$fixture"
    git init -q .
    printf 'x\n' > file.txt
    printf 'SCHEMA=1\nWORKSPACE=empty-%s\nPROJECT=%s\n' \
      "$tag" "$(basename "$fixture")" > .code-intel )
  mkdir -p "$home/.config/code-intel"
  : > "$home/.config/code-intel/projects"
}
