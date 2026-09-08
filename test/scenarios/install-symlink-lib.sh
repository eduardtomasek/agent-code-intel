# scenario: `--install` with ~/.local/lib/agent-code-intel already a symlink.
#
# The Python port refuses (issue #48, decision 60 — the target must be a real
# directory, never a symlink): `[ERROR: could not install …: it is a symlink
# …]`, exit 1, the symlink and its target untouched. The Bash reference has no
# lib directory concept and installs to ~/.local/bin regardless. Near-total
# declared divergence, same intent as install-foreign-lib.
#
# Ledger: INST-7, INST-12. Env lane only.

scenario_name()                { echo "install-symlink-lib"; }
scenario_invariants()          { echo "INST-7 INST-12"; }
scenario_args()                { echo "--install"; }
scenario_expected_divergence() { echo "exit stdout stderr manifest"; }

scenario_setup() {
  local home="$2"
  mkdir -p "$home/lib-target"
  printf 'target\n' > "$home/lib-target/marker"
  mkdir -p "$home/.local/lib"
  ln -s "$home/lib-target" "$home/.local/lib/agent-code-intel"
}
