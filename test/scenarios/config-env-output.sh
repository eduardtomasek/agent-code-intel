# scenario: defaults.env writes to both stdout and stderr and exits 0. Issue
# #38 §2.10 binds: the file's stdout goes to the tool's stdout (before its own
# output) and its stderr to the tool's stderr, "including that breakage",
# preserved 1:1. The Python port inherits both streams for the harvester, so
# --version shows the file's line, then the banner, and the stderr line lands
# on stderr — identical to the reference. Zero-divergence positive scenario.

scenario_name()       { echo "config-env-output"; }
scenario_invariants() { echo "CFG-13"; }
scenario_args()       { echo "--version"; }

scenario_setup() {
  local home="$2"
  mkdir -p "$home/.config/code-intel"
  cat > "$home/.config/code-intel/defaults.env" <<'ENV'
echo from-env-stdout
echo from-env-stderr >&2
ENV
}
