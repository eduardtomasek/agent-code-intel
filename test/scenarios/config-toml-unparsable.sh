# scenario: a defaults.toml that is not valid TOML. The Python port dies with
# the tomllib message passed straight through, prefixed with the path (issue
# #37 §7 — reformulating it would drop the line/column tomllib gives for free);
# the Bash reference ignores the file, so --version prints the banner and exits
# 0. Positive divergence (issue #35 §5).

scenario_name()                { echo "config-toml-unparsable"; }
scenario_invariants()          { echo "CFG-9"; }
scenario_args()                { echo "--version"; }
scenario_expected_divergence() { echo "exit stdout stderr"; }

scenario_setup() {
  local home="$2"
  mkdir -p "$home/.config/code-intel"
  printf 'chunk_size = = 3\n' > "$home/.config/code-intel/defaults.toml"
}
