# scenario: `--agent nope` → `[ERROR: --agent must be claude, codex or both
# (got 'nope')]`, exit 1 (RT-8). One representative of the parser's error
# family; the full flag matrix — arity, targets, defaults, repetition — is the
# unittest layer (test/unit/test_cli_parser.py, ledger RT-2).
# Read-only; zero diff against the reference.

scenario_name()       { echo "cli-flags-matrix"; }
scenario_invariants() { echo "RT-8"; }
scenario_args()       { echo "--agent nope"; }
