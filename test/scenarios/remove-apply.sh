# scenario: `--remove --apply` on a project carrying .code-intel and a pristine
# legacy refresh-intel.sh, with no stack running.
# Mutating: deletes .code-intel and refresh-intel.sh, leaves file.txt. Each
# implementation runs over its own fixture and its own workspace tag; the
# manifest diff is what proves both delete exactly the same set.

. "$(dirname -- "${BASH_SOURCE[0]}")/../lib/fixtures.sh"

scenario_name()       { echo "remove-apply"; }
scenario_invariants() { echo "RM-2 RM-4 ID-2"; }
scenario_args()       { echo "--remove --apply"; }

scenario_setup() {
  local fixture="$1" tag="$3"
  local ws="diffremove-$tag"
  ( cd "$fixture"
    git init -q .
    printf 'x\n' > file.txt
    printf 'SCHEMA=1\nWORKSPACE=%s\nPROJECT=%s\n' "$ws" "$(basename "$fixture")" > .code-intel )
  aci_write_pristine_refresh_script "$fixture" "$ws"
}
