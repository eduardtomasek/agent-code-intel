# scenario: a defaults.toml with an unknown key. The Python port reads it via
# tomllib and dies with the approved `path: unknown key '…'` text (issue #37 §5,
# §7); the Bash reference has no TOML reader and ignores the file entirely, so
# --version prints the banner and exits 0. Positive divergence (issue #35 §5).
#
# Wrong-type and unparsable-TOML errors share this code path and are covered at
# the unittest layer (test/unit/test_config.py, ledger CFG-9).

scenario_name()                { echo "config-toml-errors"; }
scenario_invariants()          { echo "CFG-3 CFG-9"; }
scenario_args()                { echo "--version"; }
scenario_expected_divergence() { echo "exit stdout stderr"; }

scenario_setup() {
  local home="$2"
  mkdir -p "$home/.config/code-intel"
  printf 'chunk_sze = 5\n' > "$home/.config/code-intel/defaults.toml"
}
