# scenario: `--path` with no argument → `[ERROR: --path requires a directory
# argument]` on stderr, exit 1 (NOT argparse's exit 2 — DEV-2 / RT-12), and
# nothing written. Also pins RT-10 (--path needs an argument).
# Read-only; zero diff against the reference.

scenario_name()       { echo "cli-parse-error-exit"; }
scenario_invariants() { echo "RT-10 RT-12 FMT-1"; }
scenario_args()       { echo "--path"; }
