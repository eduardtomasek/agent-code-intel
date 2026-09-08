# scenario: `--install` over a v2 install — the old `code-intel-init` binary in
# ~/.local/bin, the two legacy `Bash(./refresh-intel.sh)` permission rules in
# ~/.claude/settings.json, and a `defaults.env` already in place.
#
# Both implementations remove `code-intel-init` (`removed old binary -> …`),
# strip both legacy rules and add the single new one (`removed legacy …`,
# `allowed …`), and keep `defaults.env` — the resulting settings.json is
# byte-identical on both sides. As at the other install scenarios `stdout`
# (the `installed -> …` line, and the port's extra `kept …` line) and
# `manifest` (Bash file vs launcher + lib tree) are the declared divergences.
#
# Ledger: INST-3, INST-8. Env lane only.

scenario_name()                { echo "install-upgrade-v2"; }
scenario_invariants()          { echo "INST-3 INST-8"; }
scenario_args()                { echo "--install"; }
scenario_expected_divergence() { echo "stdout manifest"; }

scenario_setup() {
  local home="$2"
  mkdir -p "$home/.local/bin" "$home/.config/code-intel" "$home/.claude"
  printf '#!/usr/bin/env bash\n# code-intel-init v2\n' > "$home/.local/bin/code-intel-init"
  chmod +x "$home/.local/bin/code-intel-init"
  printf 'CHUNK_SIZE=256\n' > "$home/.config/code-intel/defaults.env"
  printf '%s\n' \
    '{"permissions": {"allow": ["Bash(./refresh-intel.sh)", "Bash(./refresh-intel.sh *)"]}}' \
    > "$home/.claude/settings.json"
}
