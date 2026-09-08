# scenario: `--install` over an existing v4 (Python) install — a
# ~/.local/lib/agent-code-intel package dir is already there (the ownership
# marker plus a stale module from a notional older 4.x), with `defaults.env`
# and the permission rule already in place.
#
# The Python port replaces the lib tree as a whole (issue #40 decision 4): the
# stale module is gone afterwards, `defaults.env` is kept (`kept …` line), the
# rule reports `already allowed`. The Bash reference has no lib concept and
# overwrites only its bin file. `stdout` and `manifest` are the declared
# divergences; the manifest diff shows `legacy_removed.py` present on the
# reference side (untouched) and absent on the candidate side (swapped out).
#
# Ledger: INST-1 (v4→v4), INST-8, INST-12. Env lane only.

scenario_name()                { echo "install-upgrade-v4"; }
scenario_invariants()          { echo "INST-1 INST-8 INST-12"; }
scenario_args()                { echo "--install"; }
scenario_expected_divergence() { echo "stdout manifest"; }

scenario_setup() {
  local home="$2"
  local pkg="$home/.local/lib/agent-code-intel/agent_code_intel"
  mkdir -p "$pkg" "$home/.config/code-intel" "$home/.claude" "$home/.local/bin"
  printf '__version__ = "3.0.0"\n' > "$pkg/__init__.py"   # the ownership marker
  printf '# removed in a later 4.x\n' > "$pkg/legacy_removed.py"
  printf '#!/usr/bin/env python3\n# an old v4 launcher\n' > "$home/.local/bin/agent-code-intel"
  chmod +x "$home/.local/bin/agent-code-intel"
  printf 'CHUNK_SIZE=256\n' > "$home/.config/code-intel/defaults.env"
  printf '{"permissions": {"allow": ["Bash(agent-code-intel --refresh)"]}}\n' \
    > "$home/.claude/settings.json"
}
