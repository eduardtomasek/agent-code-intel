# scenario: a defaults.toml where an integer key holds a string. The Python
# port dies with the approved `path: key '…' must be an integer, got string`
# text (issue #37 §5, §7); the Bash reference has no TOML reader, so --version
# prints the banner and exits 0. Positive divergence (issue #35 §5).

scenario_name()                { echo "config-toml-bad-type"; }
scenario_invariants()          { echo "CFG-9"; }
scenario_args()                { echo "--version"; }
scenario_expected_divergence() { echo "exit stdout stderr"; }

scenario_setup() {
  local home="$2"
  mkdir -p "$home/.config/code-intel"
  printf 'chunk_size = "big"\n' > "$home/.config/code-intel/defaults.toml"
}
