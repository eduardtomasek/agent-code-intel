# scenario: an unknown flag → `[ERROR: unknown flag: …]` on stderr, exit 1.
# Read-only. The one seed scenario with a NON-ZERO exit — it proves the harness
# captures and compares a failing tool's exit code and stderr (not just the
# happy path).

scenario_name()       { echo "cli-unknown-flag"; }
scenario_invariants() { echo "RT-6 RT-12 FMT-1"; }
scenario_args()       { echo "--definitely-not-a-flag"; }
