# scenario: `--status --all --json` over one registered project with no stack
# running. Read-only: exit 0 after a successful build even though every probe
# reports drift (JSON-2 / DEV-5), machine JSON on stdout, nothing written.
# Exercises the full root-key set and types (JSON-1), the `--all`-is-ignored
# enumeration (JSON-3), meta.generated_at / meta.schema (JSON-5) and the
# read-only contract (JSON-8, via the file manifest).
#
# Both sides get an equivalent config so the env lane differs only in the
# release version inside stdout/JSON; under the toml lane the candidate reads
# defaults.toml and the reference its defaults.env, so meta.config_file adds a
# second JSON difference and the config file on disk is .toml vs .env
# (manifest). Raw stdout, structural JSON and the toml manifest are declared
# locally; no other dimension is ignored.
#
# The workspace name carries the per-(impl,lane) tag so the two implementations
# never share one workspace / qdrant collection (issue #43 §4).

scenario_name()       { echo "status-json-drift"; }
scenario_invariants() { echo "JSON-1 JSON-2 JSON-3 JSON-5 JSON-8"; }
scenario_args()       { echo "--status --all --json"; }

scenario_env_config()  { printf 'CHUNK_SIZE=200\n'; }
scenario_toml_config() { printf 'chunk_size = 200\n'; }

scenario_expected_divergence() {
  if [ "${1:-}" = toml ]; then echo "stdout json manifest"; else echo "stdout json"; fi
}

scenario_setup() {
  local fixture="$1" home="$2" tag="$3"
  local ws="diffjson-$tag"
  ( cd "$fixture"
    git init -q .
    printf 'x\n' > file.txt
    printf 'SCHEMA=1\nWORKSPACE=%s\nPROJECT=%s\n' "$ws" "$(basename "$fixture")" > .code-intel )
  mkdir -p "$home/.config/code-intel"
  printf '%s\t%s\n' "$ws" "$fixture" > "$home/.config/code-intel/projects"
}
