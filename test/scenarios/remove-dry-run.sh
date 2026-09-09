# scenario: `--remove` on a project carrying removable integration artifacts.
# It must print the plan, return 2, and leave the fixture unchanged.

. "$(dirname -- "${BASH_SOURCE[0]}")/../lib/fixtures.sh"

scenario_name()       { echo "remove-dry-run"; }
scenario_invariants() { echo "RM-1"; }
scenario_args()       { echo "--remove"; }

scenario_setup() {
  local fixture="$1"
  local ws="diffremove"
  ( cd "$fixture"
    git init -q .
    printf 'x\n' > file.txt
    printf 'SCHEMA=1\nWORKSPACE=%s\nPROJECT=%s\n' "$ws" "$(basename "$fixture")" > .code-intel )
  aci_write_pristine_refresh_script "$fixture" "$ws"
}
