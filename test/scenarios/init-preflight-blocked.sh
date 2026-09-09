# scenario: `--apply` must complete the full init preflight before planning or
# mutating the project. The hermetic lane has no grepai/gitnexus/ollama, so the
# run stops with the shared dependency error and leaves the fixture untouched.
# This is the differential counterpart of the black-box preflight guard.

scenario_name()       { echo "init-preflight-blocked"; }
scenario_invariants() { echo "PREV-1 PREV-4 TOL-2"; }
scenario_args()       { echo "--apply"; }

scenario_env_config() {
  printf 'QDRANT_HOST=127.0.0.1\nQDRANT_HTTP_PORT=9\nQDRANT_PORT=9\n'
}
scenario_toml_config() {
  printf 'qdrant_host = "127.0.0.1"\nqdrant_http_port = 9\nqdrant_port = 9\n'
}

# The Python port emits its preflight rows in a slightly different order from
# the frozen Bash script; the dependency set and the untouched fixture are the
# invariant. TOML has the usual config-file manifest divergence.
scenario_expected_divergence() {
  if [ "${1:-}" = toml ]; then echo "stdout manifest"; else echo "stdout"; fi
}

scenario_setup() {
  local fixture="$1"
  ( cd "$fixture"
    git init -q .
    printf 'source\n' > source.txt )
}
