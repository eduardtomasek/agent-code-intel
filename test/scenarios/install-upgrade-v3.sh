# scenario: `--install` over a v3 install — a Bash `agent-code-intel` already in
# ~/.local/bin, a `defaults.env` already in ~/.config/code-intel, and the v3
# permission rule already in ~/.claude/settings.json.
#
# Both implementations overwrite the binary, leave `defaults.env` untouched
# (its content and hash are identical afterwards on both sides) and report the
# rule as already allowed. The Python port additionally prints the approved
# `kept … (defaults.toml not written; see --help)` line (issue #48, decision
# 10) and installs the lib tree — so `stdout` and `manifest` diverge as at
# install-clean; everything else (exit, stderr, the settings.json result) is
# identical.
#
# Ledger: INST-2, INST-8. Env lane only.

scenario_name()                { echo "install-upgrade-v3"; }
scenario_invariants()          { echo "INST-2 INST-8"; }
scenario_args()                { echo "--install"; }
scenario_expected_divergence() { echo "stdout manifest"; }

scenario_setup() {
  local home="$2"
  mkdir -p "$home/.local/bin" "$home/.config/code-intel" "$home/.claude"
  printf '#!/usr/bin/env bash\n# a v3 install\n' > "$home/.local/bin/agent-code-intel"
  chmod +x "$home/.local/bin/agent-code-intel"
  printf 'CHUNK_SIZE=256\n' > "$home/.config/code-intel/defaults.env"
  printf '{"permissions": {"allow": ["Bash(agent-code-intel --refresh)"]}}\n' \
    > "$home/.claude/settings.json"
}
