# scenario: defaults.env sets `EXTRA_IGNORES=()`. Today that passes --version /
# --help and only dies later where the array is expanded under `set -u`
# (E11–E15); the Python port treats an empty array as an empty list in both ENV
# and TOML (issue #35 DEV-14, issue #38 §2.6). Under --version both survive with
# exit 0 and identical output, so this is a zero-divergence positive scenario
# that the candidate must not regress; the "empty list, not a silent exit 1"
# fix itself is asserted at the unittest layer (ledger CFG-7).

scenario_name()       { echo "config-array-empty"; }
scenario_invariants() { echo "CFG-7"; }
scenario_args()       { echo "--version"; }

scenario_setup() {
  local home="$2"
  mkdir -p "$home/.config/code-intel"
  printf 'EXTRA_IGNORES=()\nGITIGNORE_ENTRIES=()\n' > "$home/.config/code-intel/defaults.env"
}
