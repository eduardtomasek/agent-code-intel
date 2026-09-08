# scenario: both defaults.env and defaults.toml present. The Python port checks
# for the pair before reading either and dies (issue #37 §8, TXT-5 category);
# the Bash reference has no TOML reader, sources defaults.env and runs. This is
# a positive divergence scenario (issue #35 §5) — the config files are written
# in scenario_setup so the candidate sees the conflict in both lanes.
#
# --version keeps the reference side short: it prints the banner and exits 0,
# while the candidate exits 1 before parsing (config load precedes arg-parse,
# issue #41 §4).

scenario_name()                { echo "config-both-conflict"; }
scenario_invariants()          { echo "CFG-4"; }
scenario_args()                { echo "--version"; }
scenario_expected_divergence() { echo "exit stdout stderr"; }

scenario_setup() {
  local home="$2"
  mkdir -p "$home/.config/code-intel"
  printf 'CHUNK_SIZE=1\n' > "$home/.config/code-intel/defaults.env"
  printf 'chunk_size = 1\n' > "$home/.config/code-intel/defaults.toml"
}
