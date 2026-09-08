#!/usr/bin/env bash
# test/differential.sh — hermetic differential harness.
#
# Runs one scenario against the frozen Bash reference (commit 9406cce) and a
# candidate implementation, each over its OWN fixtures, then compares the whole
# observable result as SEPARATE dimensions (issue #43 §4):
#   - exit code
#   - stdout (raw, normalized — order and whitespace are NOT normalized)
#   - stderr
#   - structural JSON (types and conditional fields; meta.generated_at is
#     format-checked then blanked) — an extra gate on top of the raw stdout diff
#   - file manifest (relative path, type, octal mode, hash of root-normalized
#     content; .git excluded)
#   - declared external effects (scenario_observe_effects)
#
# Two lanes per scenario:
#   env  — candidate + defaults.env   vs  reference + the same defaults.env
#   toml — candidate + defaults.toml   vs  reference + an equivalent defaults.env
#
# Each (lane, implementation) gets its own HOME, project, registry and workspace
# name (the qdrant collection name follows from the workspace). A mutating
# scenario therefore uses up to four independent fixtures; no implementation
# ever runs over state another run touched.
#
# CANDIDATE defaults to the reference itself. A bare run is thus reference vs
# reference and MUST produce zero diff — that is the harness proving itself.
# Point ACI_CANDIDATE at the Python launcher once it exists (issue #50+); the
# toml lane starts running for real at the same point.
#
# `set -e` is deliberately NOT used: the harness tallies scenario failures and
# reports them, it does not abort on the first one. A tool-under-test exiting
# non-zero is DATA (it is captured and compared), never a harness error. Genuine
# infrastructure failures (a broken scenario_setup) are caught explicitly.
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

aci_acquire_reference "$WORK" || exit 1
ISOLATED_PATH="$(aci_isolated_path "$WORK")" || exit 1
PYBIN="${ISOLATED_PATH%%:*}/python3"
CANDIDATE="${ACI_CANDIDATE:-$ACI_REFERENCE}"
[[ -x "$CANDIDATE" ]] || { echo "[ERROR: candidate is not executable: $CANDIDATE]" >&2; exit 1; }

CANDIDATE_IS_REFERENCE=false
[[ "$CANDIDATE" == "$ACI_REFERENCE" ]] && CANDIDATE_IS_REFERENCE=true

PASS=0; FAIL=0; UNIMPL=0; FAILED=()

# ------------------------------------------------------------------ helpers --

# normalize <fixture-root> <home-root> <tag> — stdin to stdout, replacing the
# scenario-declared volatile values with stable tokens (issue #43 §4: ONLY these
# may be normalized — not order, not whitespace, not exit, not health class, not
# the spelling of a registered path).
normalize() {
  local fx="$1" hm="$2" tag="$3"
  sed -e "s#${fx}#{FIXTURE}#g" \
      -e "s#${hm}#{HOME}#g" \
      -e "s#${tag}#{TAG}#g" \
      -e 's#"generated_at": "[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}T[0-9]\{2\}:[0-9]\{2\}:[0-9]\{2\}\(\.[0-9]*\)\{0,1\}Z"#"generated_at": "{GENERATED_AT}"#g'
}

# manifest <root> <fixture-root> <home-root> <tag> — one sorted line per entry:
# "<relpath>|<type>|<octal-mode>|<sha-of-normalized-content|->". File contents
# are normalized before hashing so two fixtures that differ only in root path or
# workspace tag hash identically; a real content difference still shows.
manifest() {
  local root="$1" fx="$2" hm="$3" tag="$4" p rel type mode sha
  ( cd "$root" 2>/dev/null || return 0
    find . -mindepth 1 \( -name .git -prune \) -o -print | LC_ALL=C sort | while IFS= read -r p; do
      rel="${p#./}"
      if [[ -L "$p" ]]; then type=l; sha="-> $(readlink "$p" | normalize "$fx" "$hm" "$tag")"
      elif [[ -d "$p" ]]; then type=d; sha="-"
      elif [[ -f "$p" ]]; then type=f; sha="$(normalize "$fx" "$hm" "$tag" < "$p" | shasum -a 256 | awk '{print $1}')"
      else type=?; sha="-"; fi
      mode="$(stat -f '%Lp' "$p")"
      printf '%s|%s|%s|%s\n' "$rel" "$type" "$mode" "$sha"
    done )
}

# json_structural_equal <norm-file-a> <norm-file-b> — 0 if both parse as JSON and
# are structurally equal (types, conditional fields, key sets); 2 if either is
# not JSON; 1 if they differ. Operates on the ROOT/TAG-normalized stdout, where a
# well-formed meta.generated_at has already been gated and blanked to
# {GENERATED_AT} by normalize(); a malformed one survives as itself and shows
# here as a difference.
json_structural_equal() {
  "$PYBIN" - "$1" "$2" <<'PY'
import json, sys

def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None

a, b = load(sys.argv[1]), load(sys.argv[2])
if a is None or b is None:
    sys.exit(2)
sys.exit(0 if a == b else 1)
PY
}

# ------------------------------------------------------------ per-run driver --

# run_one <lane> <impl> <tool> — populate $WORK/<lane>/<impl>/{exit,stdout,stderr,
# manifest,effects,.fixture_root,.home_root,.tag}. Returns non-zero only on a
# genuine infrastructure failure (a broken scenario_setup), never because the
# tool-under-test exited non-zero.
run_one() {
  local lane="$1" impl="$2" tool="$3"
  local base="$WORK/$lane/$impl" tag="$impl-$lane"
  mkdir -p "$base/project" "$base/home" || return 1

  # Hand the scenario canonical roots (/bin/pwd -P, like the tool's own canon())
  # so anything it writes — a registry line, a .code-intel PROJECT — matches what
  # the tool canonicalizes to, and normalization can substitute it cleanly. The
  # tag is a per-(impl,lane) suffix for workspace / collection names.
  local cfixture chome
  cfixture="$(cd "$base/project" && /bin/pwd -P)" || return 1
  chome="$(cd "$base/home" && /bin/pwd -P)" || return 1
  printf '%s\n' "$cfixture" > "$base/.fixture_root"
  printf '%s\n' "$chome"    > "$base/.home_root"
  printf '%s\n' "$tag"      > "$base/.tag"

  ( set -e; scenario_setup "$cfixture" "$chome" "$tag" ) || return 1

  local cfg; cfg="$(scenario_env_config "$tag")"
  if [[ -n "$cfg" ]]; then
    mkdir -p "$chome/.config/code-intel"
    printf '%s\n' "$cfg" > "$chome/.config/code-intel/defaults.env"
  fi

  local rc=0
  env -i HOME="$chome" PATH="$ISOLATED_PATH" TERM=dumb \
    bash -c "cd '$cfixture' && '$tool' $(scenario_args)" \
    > "$base/stdout" 2> "$base/stderr" || rc=$?
  printf '%s\n' "$rc" > "$base/exit"

  { manifest "$cfixture" "$cfixture" "$chome" "$tag"
    manifest "$chome" "$cfixture" "$chome" "$tag" | sed 's#^#HOME/#'; } > "$base/manifest"
  scenario_observe_effects "$cfixture" "$chome" "$tag" > "$base/effects" 2>/dev/null || true
  return 0
}

# compare <lane> — diff reference vs candidate for one lane. 0 = identical.
compare() {
  local lane="$1" ok=0 dim
  local r="$WORK/$lane/reference" c="$WORK/$lane/candidate"
  local rfx rhm rtag cfx chm ctag
  rfx="$(cat "$r/.fixture_root")"; rhm="$(cat "$r/.home_root")"; rtag="$(cat "$r/.tag")"
  cfx="$(cat "$c/.fixture_root")"; chm="$(cat "$c/.home_root")"; ctag="$(cat "$c/.tag")"

  for dim in exit stdout stderr manifest effects; do
    local rn="$c/.norm-r.$dim" cn="$c/.norm-c.$dim"
    normalize "$rfx" "$rhm" "$rtag" < "$r/$dim" > "$rn"
    normalize "$cfx" "$chm" "$ctag" < "$c/$dim" > "$cn"

    if ! diff -q "$rn" "$cn" >/dev/null; then
      printf '    %s differs:\n' "$dim"
      diff "$rn" "$cn" | sed 's/^/      /'
      ok=1
    fi

    # stdout is also checked structurally when it is JSON — a distinct dimension
    # (issue #43 §4 lists "stdout" and "JSON strukturálně" separately): catches a
    # type or conditional-field difference and is order-insensitive where the
    # text diff above is not.
    if [[ "$dim" == stdout ]]; then
      json_structural_equal "$rn" "$cn"
      case $? in
        0|2) : ;;                                 # structurally equal, or not JSON
        *) printf '    stdout (structural JSON) differs\n'; ok=1 ;;
      esac
    fi
  done
  return $ok
}

# ------------------------------------------------------------------- runner --

# run_scenario <scenario-file> — run every lane, update the tallies. Prints one
# line per lane: ok / FAIL / unimplemented / ERROR.
run_scenario() {
  local file="$1" name lane

  scenario_setup() { :; }
  scenario_env_config() { :; }
  scenario_observe_effects() { :; }
  # shellcheck disable=SC1090
  . "$file" || { printf '\n%s\n  ERROR — cannot load scenario\n' "$(basename "${file%.sh}")"; FAIL=$((FAIL+1)); FAILED+=("$(basename "${file%.sh}")"); return; }

  name="$(scenario_name)"
  printf '\n%s  [%s]\n' "$name" "$(scenario_invariants)"

  for lane in $LANES; do
    if [[ "$lane" == toml && "$CANDIDATE_IS_REFERENCE" == true ]]; then
      printf '  %-5s unimplemented — no TOML-consuming candidate yet (issue #50+)\n' "$lane"
      UNIMPL=$((UNIMPL+1))
      continue
    fi
    if ! run_one "$lane" reference "$ACI_REFERENCE" || ! run_one "$lane" candidate "$CANDIDATE"; then
      printf '  %-5s ERROR — scenario_setup failed\n' "$lane"
      FAIL=$((FAIL+1)); FAILED+=("$name/$lane")
      continue
    fi
    if compare "$lane"; then
      printf '  %-5s ok\n' "$lane"
      PASS=$((PASS+1))
    else
      printf '  %-5s FAIL\n' "$lane"
      FAIL=$((FAIL+1)); FAILED+=("$name/$lane")
    fi
  done
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
echo "python3:   $("$PYBIN" --version 2>&1)"

for f in "${SELECTED[@]}"; do
  [[ -f "$f" ]] || { echo "[ERROR: no such scenario: $f]" >&2; FAIL=$((FAIL+1)); FAILED+=("$(basename "${f%.sh}")"); continue; }
  run_scenario "$f"
done

printf '\n%d passed, %d failed, %d unimplemented\n' "$PASS" "$FAIL" "$UNIMPL"
if (( FAIL > 0 )); then printf 'failed: %s\n' "${FAILED[*]}"; exit 1; fi
