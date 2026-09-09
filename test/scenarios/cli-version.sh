# scenario: --version prints the product name + version and exits 0.
# Read-only. The reference remains pinned to 3.0.0 while the switched
# candidate reports 4.1.0, so stdout is the one approved release divergence.
# This still exercises the exit / stdout / stderr dimensions and the parser's
# in-loop early exit.
#
# scenario_invariants() lists the ledger IDs this scenario WILL carry once a
# real candidate exists; against the reference alone it proves only the harness.

scenario_name()       { echo "cli-version"; }
scenario_invariants() { echo "RT-2 RT-4 RT-5 CFG-8"; }
scenario_args()       { echo "--version"; }
scenario_expected_divergence() { echo "stdout"; }
