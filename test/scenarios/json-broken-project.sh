# scenario: `--status --all --json` with a registered project whose .code-intel
# is malformed. The JSON entry for it is the short shape
# `{workspace, path, code_intel_error, ok:false}` — no name/exists/probe fields
# (JSON-6) — and the run still exits 0 (JSON-2). A second, healthy row keeps the
# enumeration honest.
#
# env lane byte-identical; toml lane diverges on meta.config_file (stdout) and
# the .toml-vs-.env config file on disk (manifest).

scenario_name()       { echo "json-broken-project"; }
scenario_invariants() { echo "JSON-2 JSON-6"; }
scenario_args()       { echo "--status --all --json"; }

scenario_env_config()  { printf 'CHUNK_SIZE=200\n'; }
scenario_toml_config() { printf 'chunk_size = 200\n'; }

scenario_expected_divergence() { [ "${1:-}" = toml ] && echo "stdout manifest" || true; }

scenario_setup() {
  local fixture="$1" home="$2" tag="$3"
  local ok="$fixture/ok" bad="$fixture/bad"
  mkdir -p "$ok" "$bad"
  ( cd "$ok" && git init -q . && printf 'x\n' > f.txt
    printf 'SCHEMA=1\nWORKSPACE=ok-%s\nPROJECT=ok\n' "$tag" > .code-intel )
  ( cd "$bad" && git init -q .
    printf 'SCHEMA=1\nWORKSPACE=x\nPROJECT=x\nBOGUS=1\n' > .code-intel )
  mkdir -p "$home/.config/code-intel"
  {
    printf 'ok-%s\t%s\n'  "$tag" "$ok"
    printf 'bad-%s\t%s\n' "$tag" "$bad"
  } > "$home/.config/code-intel/projects"
}
