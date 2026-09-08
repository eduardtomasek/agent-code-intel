#!/usr/bin/env bash
# test/differential.sh — hermetic differential harness.
#
# Runs one scenario against the frozen Bash reference (commit 9406cce) and a
# candidate implementation, each over its OWN fixtures, then compares the whole
# observable result: exit code, stdout, stderr, structural JSON, a file manifest
# (type + mode + content hash), and any declared external effects.
#
# Two lanes per scenario (issue #43 §4):
#   env  — candidate + defaults.env   vs  reference + the same defaults.env
#   toml — candidate + defaults.toml   vs  reference + an equivalent defaults.env
#
# A mutating scenario therefore uses up to four independent fixtures; no
# implementation ever runs over state another run already touched.
#
# CANDIDATE defaults to the reference itself. A bare run is thus reference vs
# reference and MUST produce zero diff — that is the harness proving itself.
# Point ACI_CANDIDATE at the Python launcher once it exists (issue #50+); the
# toml lane starts running for real at the same point.
#
# Usage:
#   test/differential.sh                      # every scenario, env lane
#   test/differential.sh cli-version          # one scenario
#   ACI_CANDIDATE=./agent-code-intel test/differential.sh
#   ACI_LANES="env toml" test/differential.sh

set -uo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/lib/reference.sh"
. "$HERE/lib/isolated_path.sh"

SCENARIO_DIR="$HERE/scenarios"
LANES="${ACI_LANES:-env}"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

aci_acquire_reference "$WORK"
ISOLATED_PATH="$(aci_isolated_path "$WORK")"
CANDIDATE="${ACI_CANDIDATE:-$ACI_REFERENCE}"
[[ -x "$CANDIDATE" ]] || { echo "[ERROR: candidate is not executable: $CANDIDATE]" >&2; exit 1; }

CANDIDATE_IS_REFERENCE=false
[[ "$CANDIDATE" == "$ACI_REFERENCE" ]] && CANDIDATE_IS_REFERENCE=true

PASS=0; FAIL=0; UNIMPL=0; FAILED=()

# ------------------------------------------------------------------ helpers --

# normalize <fixture-root> <home-root> — stdin to stdout, replacing the volatile
# roots and the JSON timestamp with stable tokens (issue #43 §4: only
# scenario-declared values may be normalized).
normalize() {
  local fx="$1" hm="$2"
  sed -e "s#${fx}#{FIXTURE}#g" -e "s#${hm}#{HOME}#g"
}
# meta.generated_at is the one other declared-volatile value; it lives only in
# JSON stdout and json_structural_equal validates its format and blanks it
# there. No plain-text stream carries a timestamp.

# manifest <root> <fixture-root> <home-root> — one sorted line per entry:
# "<relpath>|<type>|<octal-mode>|<sha-of-normalized-content|->". File contents
# are normalized before hashing so two fixtures that differ only in their root
# path hash identically; a real content difference still shows. .git is excluded
# (two independent `git init`s differ in reflog/index mtimes, never in anything
# a scenario asserts).
manifest() {
  local root="$1" fx="$2" hm="$3" p rel type mode sha
  ( cd "$root" 2>/dev/null || return 0
    find . -mindepth 1 \( -name .git -prune \) -o -print | LC_ALL=C sort | while IFS= read -r p; do
      rel="${p#./}"
      if [[ -L "$p" ]]; then type=l; sha="-> $(readlink "$p" | normalize "$fx" "$hm")"
      elif [[ -d "$p" ]]; then type=d; sha="-"
      elif [[ -f "$p" ]]; then type=f; sha="$(normalize "$fx" "$hm" < "$p" | shasum -a 256 | awk '{print $1}')"
      else type=?; sha="-"; fi
      mode="$(stat -f '%Lp' "$p")"
      printf '%s|%s|%s|%s\n' "$rel" "$type" "$mode" "$sha"
    done )
}

# json_structural_equal <file-a> <file-b> — exit 0 if both are JSON and equal
# after blanking meta.generated_at; exit 2 if either is not JSON; 1 if they differ.
json_structural_equal() {
  "${ISOLATED_PATH%%:*}/python3" - "$1" "$2" <<'PY'
import json, re, sys

TS = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$')

def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None

a, b = load(sys.argv[1]), load(sys.argv[2])
if a is None or b is None:
    sys.exit(2)

for d in (a, b):
    meta = d.get("meta") if isinstance(d, dict) else None
    if isinstance(meta, dict) and "generated_at" in meta:
        if not (isinstance(meta["generated_at"], str) and TS.match(meta["generated_at"])):
            print("meta.generated_at is not an ISO-8601 Z timestamp: %r" % meta["generated_at"])
            sys.exit(1)
        meta["generated_at"] = "{GENERATED_AT}"

sys.exit(0 if a == b else 1)
PY
}

# ------------------------------------------------------------ per-run driver --

# run_one <lane> <impl> <tool> — populate $WORK/<lane>/<impl>/{exit,stdout,stderr,manifest,effects}
run_one() {
  local lane="$1" impl="$2" tool="$3"
  local base="$WORK/$lane/$impl"
  mkdir -p "$base/project" "$base/home"

  # Hand the scenario canonical roots (/bin/pwd -P, like the tool's own canon())
  # so anything it writes — a registry line, a .code-intel PROJECT — matches what
  # the tool canonicalizes to, and normalization can substitute it cleanly.
  local cfixture chome
  cfixture="$(cd "$base/project" && /bin/pwd -P)"
  chome="$(cd "$base/home" && /bin/pwd -P)"

  scenario_setup "$cfixture" "$chome"

  local cfg; cfg="$(scenario_env_config)"
  if [[ -n "$cfg" ]]; then
    mkdir -p "$chome/.config/code-intel"
    printf '%s\n' "$cfg" > "$chome/.config/code-intel/defaults.env"
  fi

  printf '%s\n' "$cfixture" > "$base/.fixture_root"
  printf '%s\n' "$chome"    > "$base/.home_root"

  env -i HOME="$chome" PATH="$ISOLATED_PATH" TERM=dumb \
    bash -c "cd '$cfixture' && '$tool' $(scenario_args)" \
    > "$base/stdout" 2> "$base/stderr"
  printf '%s\n' "$?" > "$base/exit"

  { manifest "$cfixture" "$cfixture" "$chome"
    manifest "$chome" "$cfixture" "$chome" | sed 's#^#HOME/#'; } > "$base/manifest"
  scenario_observe_effects "$cfixture" "$chome" > "$base/effects" 2>/dev/null || true
}

# compare <lane> — diff reference vs candidate for one lane; returns 0/1.
compare() {
  local lane="$1" ok=0 dim
  local r="$WORK/$lane/reference" c="$WORK/$lane/candidate"
  local rfx rhm cfx chm
  rfx="$(cat "$r/.fixture_root")"; rhm="$(cat "$r/.home_root")"
  cfx="$(cat "$c/.fixture_root")"; chm="$(cat "$c/.home_root")"

  # manifest was already hashed over normalized content; exit/stderr/effects are
  # plain text; stdout may be JSON.
  for dim in exit stdout stderr manifest effects; do
    local rn="$c/.rn.$dim" cn="$c/.cn.$dim"
    normalize "$rfx" "$rhm" < "$r/$dim" > "$rn"
    normalize "$cfx" "$chm" < "$c/$dim" > "$cn"

    if [[ "$dim" == stdout ]]; then
      # $rn/$cn have normalized roots but intact timestamps; the comparator
      # validates meta.generated_at's format and blanks it structurally.
      json_structural_equal "$rn" "$cn"
      case $? in
        0) continue ;;
        1) printf '    stdout (structural JSON) differs:\n'; diff "$rn" "$cn" | sed 's/^/      /'; ok=1; continue ;;
        *) : ;;  # not JSON — fall through to text compare
      esac
    fi

    if ! diff -q "$rn" "$cn" >/dev/null; then
      printf '    %s differs:\n' "$dim"
      diff "$rn" "$cn" | sed 's/^/      /'
      ok=1
    fi
  done
  return $ok
}

# ------------------------------------------------------------------- runner --

run_scenario() {
  local file="$1" name
  ( set -e
    unset -f scenario_setup scenario_env_config scenario_observe_effects 2>/dev/null || true
    # defaults — a scenario overrides only what it needs
    scenario_setup() { :; }
    scenario_env_config() { :; }
    scenario_observe_effects() { :; }
    . "$file"

    name="$(scenario_name)"
    printf '\n%s  [%s]\n' "$name" "$(scenario_invariants)"

    for lane in $LANES; do
      if [[ "$lane" == toml && "$CANDIDATE_IS_REFERENCE" == true ]]; then
        printf '  %-5s unimplemented — no TOML-consuming candidate yet (issue #50+)\n' "$lane"
        exit 3
      fi
      run_one "$lane" reference "$ACI_REFERENCE"
      run_one "$lane" candidate "$CANDIDATE"
      if compare "$lane"; then
        printf '  %-5s ok\n' "$lane"
      else
        printf '  %-5s FAIL\n' "$lane"
        exit 1
      fi
    done )
  local rc=$?
  case $rc in
    0) PASS=$((PASS+1)) ;;
    3) UNIMPL=$((UNIMPL+1)); PASS=$((PASS+1)) ;;  # unimplemented lane is reported, not counted as failure
    *) FAIL=$((FAIL+1)); FAILED+=("$(basename "${1%.sh}")") ;;
  esac
}

SELECTED=()
if [[ $# -gt 0 ]]; then
  for a in "$@"; do SELECTED+=("$SCENARIO_DIR/${a%.sh}.sh"); done
else
  for f in "$SCENARIO_DIR"/*.sh; do SELECTED+=("$f"); done
fi

echo "reference: $ACI_REFERENCE_COMMIT:agent-code-intel"
echo "candidate: $CANDIDATE$([[ "$CANDIDATE_IS_REFERENCE" == true ]] && echo '  (= reference; harness self-check)')"
echo "lanes:     $LANES"
echo "python3:   $("${ISOLATED_PATH%%:*}/python3" --version 2>&1)"

for f in "${SELECTED[@]}"; do
  [[ -f "$f" ]] || { echo "[ERROR: no such scenario: $f]" >&2; FAIL=$((FAIL+1)); continue; }
  run_scenario "$f"
done

printf '\n%d passed, %d failed' "$PASS" "$FAIL"
[[ $UNIMPL -gt 0 ]] && printf ' (%d lane(s) unimplemented)' "$UNIMPL"
printf '\n'
if (( FAIL > 0 )); then printf 'failed: %s\n' "${FAILED[*]}"; exit 1; fi
