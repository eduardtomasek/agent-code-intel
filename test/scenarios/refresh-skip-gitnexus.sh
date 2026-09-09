# scenario: `--refresh --no-gitnexus` on a set-up project with nothing
# installed. --no-gitnexus skips the gitnexus + git preflight checks
# (`9406cce` :2012); only the grepai side is checked — grepai, qdrant and ollama
# are all unreachable, so the run exits 1 with a `found 3 unmet dependencies`
# block (REF-3 / REF-4). Zero divergence in both lanes.
#
# qdrant is pointed at a closed local port so `curl` fails fast on both sides
# (see refresh-preflight-blocked).

scenario_name()       { echo "refresh-skip-gitnexus"; }
scenario_invariants() { echo "REF-3 REF-4"; }
scenario_args()       { echo "--refresh --no-gitnexus"; }

scenario_env_config() {
  printf 'QDRANT_HOST=127.0.0.1\nQDRANT_HTTP_PORT=9\nQDRANT_PORT=9\n'
}
scenario_toml_config() {
  printf 'qdrant_host = "127.0.0.1"\nqdrant_http_port = 9\nqdrant_port = 9\n'
}

# Only the config file on disk differs (.toml vs .env); --refresh output carries
# no config path, so the toml lane declares just the manifest (issue #37 §7).
scenario_expected_divergence() { [ "${1:-}" = toml ] && echo "manifest" || true; }

scenario_setup() {
  local fixture="$1" tag="$3"
  ( cd "$fixture"
    git init -q .
    printf 'x\n' > file.txt
    printf 'SCHEMA=1\nWORKSPACE=skipgn-%s\nPROJECT=%s\n' \
      "$tag" "$(basename "$fixture")" > .code-intel )
}
