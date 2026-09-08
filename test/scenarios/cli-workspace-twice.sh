# scenario: a second positional → `[ERROR: workspace name given twice ('foo'
# and 'bar')]`, exit 1 (RT-7). Read-only; zero diff against the reference.

scenario_name()       { echo "cli-workspace-twice"; }
scenario_invariants() { echo "RT-7 FMT-1"; }
scenario_args()       { echo "foo bar"; }
