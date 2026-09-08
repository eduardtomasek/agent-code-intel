# scenario: plain `--status` on a set-up project with no stack running. The
# text table carries health in the exit code: every probe reports drift, so the
# single row is `DRIFT`, the run ends `Repair a project with: …` and exits 2
# (RT-5 / ID-8). The header (Project / Workspace / Agents) and the `hr` rule
# are byte-identical.
#
# The text table has no meta.config_file line and this scenario needs no config
# override, so no config file is written at all — zero divergence in both lanes.

scenario_name()       { echo "status-text-drift"; }
scenario_invariants() { echo "ID-7 ID-8 RT-5 FMT-3 FMT-4"; }
scenario_args()       { echo "--status"; }

scenario_setup() {
  local fixture="$1" tag="$3"
  ( cd "$fixture"
    git init -q .
    printf 'x\n' > file.txt
    printf 'SCHEMA=1\nWORKSPACE=textdrift-%s\nPROJECT=%s\n' \
      "$tag" "$(basename "$fixture")" > .code-intel )
}
