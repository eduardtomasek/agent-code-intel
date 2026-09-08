# scenario: `--install` with someone else's directory already sitting at
# ~/.local/lib/agent-code-intel (no `agent_code_intel/__init__.py` marker).
#
# The Python port refuses before touching anything (issue #48, decision 60):
# `[ERROR: could not install …: it exists but is not an agent-code-intel
# install …]`, exit 1, the foreign directory untouched. The Bash reference has
# no lib directory concept at all — it installs its single file to ~/.local/bin
# and exits 0, oblivious to ~/.local/lib. So this is a near-total declared
# divergence (exit, stdout, stderr, manifest); its point is to pin that the
# reference is unaffected and the port aborts cleanly.
#
# Ledger: INST-6, INST-12. Env lane only.

scenario_name()                { echo "install-foreign-lib"; }
scenario_invariants()          { echo "INST-6 INST-12"; }
scenario_args()                { echo "--install"; }
scenario_expected_divergence() { echo "exit stdout stderr manifest"; }

scenario_setup() {
  local home="$2"
  mkdir -p "$home/.local/lib/agent-code-intel/somedir"
  printf 'not ours\n' > "$home/.local/lib/agent-code-intel/README"
}
