# scenario: the Python launcher, run by an interpreter below 3.11, prints the
# approved one-line diagnostic to stderr and exits 1 — where the Bash reference
# just runs. This is approved divergence DEV-1 / text TXT-2 (issue #35 §5): a
# positive scenario with an exact local diff, not a global ignore.
#
# scenario_path_override drops the default 3.11 isolate for the machine's
# /usr/bin:/bin, whose python3 is 3.9.6 — enough to make the candidate's gate
# fire. Still hermetic: no grepai / gitnexus / ollama / node / claude / codex.
#
# Only meaningful with a real candidate. Reference-vs-reference (the bare
# self-check) sees zero diff and then fails the "declared divergence did not
# differ" guard — so this scenario is run only with ACI_CANDIDATE set.

scenario_name()                { echo "runtime-gate"; }
scenario_invariants()          { echo "RT-11"; }
scenario_args()                { echo "--version"; }
scenario_path_override()       { echo "/usr/bin:/bin"; }
scenario_expected_divergence() { echo "exit stdout stderr"; }
