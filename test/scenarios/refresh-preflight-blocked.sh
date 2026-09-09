# scenario: `--refresh` on a set-up project with nothing installed. The lighter
# refresh preflight (`9406cce` :1984) checks grepai / qdrant / ollama / gitnexus
# / git, prints a `MISSING` row per unmet dependency to stdout, then a
# multi-line `[ERROR: refresh preflight found N unmet dependencies — nothing was
# refreshed]` block to stderr, and exits 1 without touching anything
# (REF-4 / FMT-5 / TOL-2). Zero divergence in both lanes.
#
# qdrant is pointed at a closed local port so `curl` fails connection-refused
# fast on BOTH sides — the reference's probe has no timeout (DEV-15), and a real
# half-dead qdrant on the default 6333 would hang it. git lives on the isolated
# PATH, so its row is `ok`; everything else is `MISSING`.

scenario_name()       { echo "refresh-preflight-blocked"; }
scenario_invariants() { echo "REF-4 FMT-5 TOL-2"; }
scenario_args()       { echo "--refresh"; }

scenario_env_config() {
  printf 'QDRANT_HOST=127.0.0.1\nQDRANT_HTTP_PORT=9\nQDRANT_PORT=9\n'
}
scenario_toml_config() {
  printf 'qdrant_host = "127.0.0.1"\nqdrant_http_port = 9\nqdrant_port = 9\n'
}

# --refresh prints no config-file path, so stdout/stderr are byte-identical in
# both lanes; only the config file on disk differs (.toml vs .env) — declared
# for the toml lane alone, same as the status-json scenarios (issue #37 §7).
scenario_expected_divergence() { [ "${1:-}" = toml ] && echo "manifest" || true; }

scenario_setup() {
  local fixture="$1" tag="$3"
  ( cd "$fixture"
    git init -q .
    printf 'x\n' > file.txt
    printf 'SCHEMA=1\nWORKSPACE=preflight-%s\nPROJECT=%s\n' \
      "$tag" "$(basename "$fixture")" > .code-intel )
}
