# scenario: `--refresh` in a git repo that has no `.code-intel`. --refresh never
# founds a project (`9406cce` :559 vs project.resolve_project's ABSENT+refresh
# branch): both implementations die with the identical
# `no .code-intel in <dir> — this project has not been set up; run: …` before
# any mode work, and nothing is written. Exit 1 (REF-1 / REF-4). Zero
# divergence in both lanes.

scenario_name()       { echo "refresh-no-code-intel"; }
scenario_invariants() { echo "REF-1 REF-4"; }
scenario_args()       { echo "--refresh"; }

scenario_setup() {
  local fixture="$1"
  ( cd "$fixture"
    git init -q .
    printf 'x\n' > file.txt )
}
