# scenario: `--status --all` over a registry holding four rows — a healthy-ish
# .code-intel project (drift, no stack), one whose .code-intel is malformed
# (BROKEN row, not a die — the loop must keep going), one whose directory is
# gone (GONE row), and one with no .code-intel at all (ABSENT — a normal state,
# reported under its basename). Exit 2. Proves the registry loop, the row
# vocabulary and that one broken project does not hide the rest (ID-7, and the
# regression the reference's test_status_all_continues_past_broken_code_intel
# pins).
#
# Text mode with no config file written: zero divergence in both lanes.

scenario_name()       { echo "status-all-registry"; }
scenario_invariants() { echo "ID-7 ID-8 TOL-1"; }
scenario_args()       { echo "--status --all"; }

scenario_setup() {
  local fixture="$1" home="$2" tag="$3"
  local good="$fixture/good" broken="$fixture/broken" absent="$fixture/absent"
  mkdir -p "$good" "$broken" "$absent"
  ( cd "$good" && git init -q . && printf 'x\n' > f.txt
    printf 'SCHEMA=1\nWORKSPACE=good-%s\nPROJECT=good\n' "$tag" > .code-intel )
  ( cd "$broken" && git init -q .
    printf 'SCHEMA=1\nworkspace=lowercase-is-invalid\nPROJECT=broken\n' > .code-intel )
  ( cd "$absent" && git init -q . && printf 'x\n' > f.txt )
  mkdir -p "$home/.config/code-intel"
  {
    printf 'good-%s\t%s\n'  "$tag" "$good"
    printf 'broken-%s\t%s\n' "$tag" "$broken"
    printf 'gone-%s\t%s\n'   "$tag" "$fixture/vanished"
    printf 'absent-%s\t%s\n' "$tag" "$absent"
  } > "$home/.config/code-intel/projects"
}
