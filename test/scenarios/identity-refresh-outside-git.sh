# scenario: `--refresh` from a directory that is not inside a git repo. Both
# implementations resolve the nearest git root first and fail to find one,
# before any mode work (`9406cce` :522 vs project.resolve_project).
#
# The reference interpolates an EMPTY path into the message: `ROOT="$(git …)"`
# blanks ROOT on failure, then `|| die "… $ROOT …"` reads the now-empty value.
# The Python port carries the real directory instead — approved fix DEV-3 /
# text exception TXT-4 (issue #35 deviation 3). Only stderr diverges.

scenario_name()                { echo "identity-refresh-outside-git"; }
scenario_invariants()          { echo "ID-3 REF-1 REF-6"; }
scenario_args()                { echo "--refresh"; }
scenario_expected_divergence() { echo "stderr"; }

scenario_setup() {
  local fixture="$1"
  printf 'x\n' > "$fixture/file.txt"
}
