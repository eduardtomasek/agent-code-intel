# scenario: defaults.env does `unset QDRANT_HOST`. The Bash reference presets it
# then dies on the unbound variable at :128 with bash's own line-numbered
# message; the Python harvester detects the unset transferred name and dies with
# its own approved text (issue #38 §2.7, TXT-7). Both exit 1 with empty stdout,
# so only stderr diverges (issue #35 §5, deviation-list text exception 7).

scenario_name()                { echo "config-unset-name"; }
scenario_invariants()          { echo "CFG-11"; }
scenario_args()                { echo "--version"; }
scenario_expected_divergence() { echo "stderr"; }

scenario_setup() {
  local home="$2"
  mkdir -p "$home/.config/code-intel"
  printf 'unset QDRANT_HOST\n' > "$home/.config/code-intel/defaults.env"
}
