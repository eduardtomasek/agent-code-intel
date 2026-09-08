# scenario: defaults.env sets VERSION=9.9.9. The Bash reference sources it before
# --version and prints `agent-code-intel 9.9.9` (trap P3, :90 before :126); the
# Python port keeps __version__ as a module constant and never transfers VERSION,
# so it prints `agent-code-intel 3.0.0`. Approved narrowing DEV-13 / CFG-8
# (issue #35 deviation 13). Only stdout diverges — both exit 0, stderr empty.

scenario_name()                { echo "config-version-not-overridable"; }
scenario_invariants()          { echo "CFG-8"; }
scenario_args()                { echo "--version"; }
scenario_expected_divergence() { echo "stdout"; }

scenario_setup() {
  local home="$2"
  mkdir -p "$home/.config/code-intel"
  printf 'VERSION=9.9.9\n' > "$home/.config/code-intel/defaults.env"
}
