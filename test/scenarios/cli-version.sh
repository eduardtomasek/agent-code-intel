# scenario: --version prints the pinned name + version and exits 0.
# Read-only. Exercises the exit / stdout / stderr dimensions and the parser's
# in-loop early exit.
#
# scenario_invariants() lists the ledger IDs this scenario WILL carry once a
# real candidate exists; against the reference alone it proves only the harness.

scenario_name()       { echo "cli-version"; }
scenario_invariants() { echo "RT-2 RT-4 RT-5 CFG-8"; }
scenario_args()       { echo "--version"; }
