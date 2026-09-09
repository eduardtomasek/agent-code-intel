# scenario: `--refresh --no-grepai` on a set-up project with nothing installed.
# --no-grepai skips the grepai / qdrant / ollama preflight checks entirely
# (`9406cce` :1987); only the gitnexus side is checked, and gitnexus is missing
# from the isolated PATH, so the run still exits 1 — but with a single-line
# `found 1 unmet dependency` block (REF-3 / REF-4). git is present, so its row
# is `ok`. Zero divergence in both lanes; no config needed (qdrant is never
# probed).

scenario_name()       { echo "refresh-skip-grepai"; }
scenario_invariants() { echo "REF-3 REF-4"; }
scenario_args()       { echo "--refresh --no-grepai"; }

scenario_setup() {
  local fixture="$1" tag="$3"
  ( cd "$fixture"
    git init -q .
    printf 'x\n' > file.txt
    printf 'SCHEMA=1\nWORKSPACE=skipgrepai-%s\nPROJECT=%s\n' \
      "$tag" "$(basename "$fixture")" > .code-intel )
}
