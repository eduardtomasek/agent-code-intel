# scenario: `--refresh --no-grepai --no-gitnexus` on a set-up project. Both
# flags skip a side's preflight, re-index AND audit, so this is the one full
# non-error path through --refresh that a hermetic harness can run end to end
# (`9406cce` :1987/:2012/:2047/:2091). The preflight header, the
# `code-intel refresh — <root>` heading (em dash = 3 bytes under the C locale
# the harness runs in), the blank lines and the closing `Code intelligence is
# fresh.` are byte-identical; exit 0 (REF-3 / REF-4). Zero divergence in both
# lanes.

scenario_name()       { echo "refresh-skip-both"; }
scenario_invariants() { echo "REF-2 REF-3 REF-4 FMT-2 FMT-4"; }
scenario_args()       { echo "--refresh --no-grepai --no-gitnexus"; }

scenario_setup() {
  local fixture="$1" tag="$3"
  ( cd "$fixture"
    git init -q .
    printf 'x\n' > file.txt
    printf 'SCHEMA=1\nWORKSPACE=skipboth-%s\nPROJECT=%s\n' \
      "$tag" "$(basename "$fixture")" > .code-intel )
}
