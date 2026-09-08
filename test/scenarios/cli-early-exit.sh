# scenario: `-h` followed by garbage → the usage text on stdout, exit 0. Proves
# `--help` is handled in the parse loop and short-circuits everything to its
# right (RT-4), and that usage goes to stdout (RT-14).
# Read-only; zero diff against the reference.

scenario_name()       { echo "cli-early-exit"; }
scenario_invariants() { echo "RT-4 RT-14"; }
scenario_args()       { echo "-h --definitely-not-a-flag"; }
