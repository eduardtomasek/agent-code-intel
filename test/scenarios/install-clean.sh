# scenario: `--install` onto a pristine machine (no prior binary, no config, no
# ~/.claude). Both implementations lay down a launcher, an on-PATH advisory, a
# config file and the exact `Bash(agent-code-intel --refresh)` permission rule
# — byte-identical where it matters (exit 0, empty stderr, the permission and
# PATH lines).
#
# The install ARTIFACT necessarily diverges (issue #35, DEV-1 / TXT-1 / TXT-8):
# the reference copies its single Bash file to ~/.local/bin and writes
# defaults.env; the Python port writes a thin launcher plus a ~/.local/lib
# package tree and a defaults.toml. So `stdout` (the `installed -> …` and
# `wrote …` lines) and `manifest` are declared, expected divergences; the diff
# printed for each is reviewed to confirm nothing else moved.
#
# Ledger: INST-1, INST-8, INST-11. Env lane only (there is no config to feed).

scenario_name()                { echo "install-clean"; }
scenario_invariants()          { echo "INST-1 INST-8 INST-11"; }
scenario_args()                { echo "--install"; }
scenario_expected_divergence() { echo "stdout manifest"; }
