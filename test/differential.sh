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
# A scenario may declare an approved divergence (issue #35 §5) with
# `scenario_expected_divergence` (echo the dimensions that are allowed — and
# required — to differ: e.g. "exit stdout stderr"). It is called once per lane
# with the lane name ("env" / "toml") as $1, so a divergence that exists in
# only one lane can be declared for that lane alone — e.g. the port's
# `--status --json` meta.config_file matches the reference byte-for-byte with a
# defaults.env (env lane) but names defaults.toml under the toml lane (issue #37
# §7). A scenario that ignores $1 keeps the old whole-scenario behaviour.
#
# A scenario may also run under a non-default PATH with `scenario_path_override`
# (still hermetic — used only so the runtime-gate scenario reaches the machine's
# sub-3.11 python3).
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
# Each scenario runs the tool after `cd`-ing into its fixture, so a relative
# candidate path (ACI_CANDIDATE=./agent-code-intel.py) must be made absolute.
CANDIDATE="$(cd "$(dirname "$CANDIDATE")" && pwd)/$(basename "$CANDIDATE")"

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
  # A fresh tree per scenario: selecting several scenarios in one run reuses
  # $WORK, so config / registry files one scenario writes must not leak into
  # the next.
  rm -rf "$base" || return 1
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

  # env lane: both implementations get scenario_env_config as defaults.env.
  # toml lane: the reference still gets defaults.env (it has no TOML reader),
  # the candidate gets scenario_toml_config as defaults.toml — "candidate +
  # defaults.toml vs reference + an equivalent defaults.env" (issue #43 §4).
  local cfg cfg_file="defaults.env"
  if [[ "$lane" == toml && "$impl" == candidate ]]; then
    cfg="$(scenario_toml_config "$tag")"
    cfg_file="defaults.toml"
  else
    cfg="$(scenario_env_config "$tag")"
  fi
  if [[ -n "$cfg" ]]; then
    mkdir -p "$chome/.config/code-intel"
    printf '%s\n' "$cfg" > "$chome/.config/code-intel/$cfg_file"
  fi

  # A scenario may run under a different PATH than the default 3.11 isolate —
  # the runtime-gate scenario needs the machine's sub-3.11 /usr/bin/python3 to
  # make the candidate's gate fire (issue #35, DEV-1). Everything else stays
  # hermetic: still no grepai / gitnexus / ollama / node / claude / codex.
  local run_path; run_path="$(scenario_path_override)"
  [[ -n "$run_path" ]] || run_path="$ISOLATED_PATH"

  # PYTHONDONTWRITEBYTECODE: a Python candidate must not leave interpreter
  # bytecode caches (~/Library/Caches or a source __pycache__) in the manifest
  # — that is noise, not one of the tool's own writes. Harmless for the Bash
  # reference.
  local rc=0
  env -i HOME="$chome" PATH="$run_path" TERM=dumb PYTHONDONTWRITEBYTECODE=1 \
    bash -c "cd '$cfixture' && '$tool' $(scenario_args)" \
    > "$base/stdout" 2> "$base/stderr" || rc=$?
  printf '%s\n' "$rc" > "$base/exit"

  { manifest "$cfixture" "$cfixture" "$chome" "$tag"
    manifest "$chome" "$cfixture" "$chome" "$tag" | sed 's#^#HOME/#'; } > "$base/manifest"
  scenario_observe_effects "$cfixture" "$chome" "$tag" > "$base/effects" 2>/dev/null || true
  return 0
}

# compare <lane> — diff reference vs candidate for one lane. 0 = identical,
# OR every dimension that differs is one the scenario declared as an approved
# divergence (issue #35 §5: a known divergence is a positive scenario with an
# exact local diff, never a global ignore list) AND every declared divergence
# dimension actually did differ (a stale "expected" divergence is a failure).
compare() {
  local lane="$1" ok=0 dim
  local r="$WORK/$lane/reference" c="$WORK/$lane/candidate"
  local rfx rhm rtag cfx chm ctag
  rfx="$(cat "$r/.fixture_root")"; rhm="$(cat "$r/.home_root")"; rtag="$(cat "$r/.tag")"
  cfx="$(cat "$c/.fixture_root")"; chm="$(cat "$c/.home_root")"; ctag="$(cat "$c/.tag")"

  local expdiv=" $(scenario_expected_divergence "$lane") " seen_div=" "

  for dim in exit stdout stderr manifest effects; do
    local rn="$c/.norm-r.$dim" cn="$c/.norm-c.$dim"
    normalize "$rfx" "$rhm" "$rtag" < "$r/$dim" > "$rn"
    normalize "$cfx" "$chm" "$ctag" < "$c/$dim" > "$cn"

    if ! diff -q "$rn" "$cn" >/dev/null; then
      if [[ "$expdiv" == *" $dim "* ]]; then
        printf '    %s differs — approved divergence:\n' "$dim"
        diff "$rn" "$cn" | sed 's/^/      /'
        seen_div="$seen_div$dim "
        continue
      fi
      printf '    %s differs:\n' "$dim"
      diff "$rn" "$cn" | sed 's/^/      /'
      ok=1
    fi

    # stdout is also checked structurally when it is JSON — a distinct dimension
    # (issue #43 §4 lists "stdout" and "JSON strukturálně" separately): catches a
    # type or conditional-field difference and is order-insensitive where the
    # text diff above is not.
    if [[ "$dim" == stdout && "$expdiv" != *" stdout "* ]]; then
      json_structural_equal "$rn" "$cn"
      case $? in
        0|2) : ;;                                 # structurally equal, or not JSON
        *) printf '    stdout (structural JSON) differs\n'; ok=1 ;;
      esac
    fi
  done

  # Every dimension the scenario declared as an approved divergence must have
  # actually diverged — otherwise the scenario is asserting a divergence that
  # no longer exists.
  for dim in $(scenario_expected_divergence "$lane"); do
    [[ "$seen_div" == *" $dim "* ]] || {
      printf '    %s was declared an approved divergence but did not differ\n' "$dim"
      ok=1
    }
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
  scenario_toml_config() { :; }
  scenario_observe_effects() { :; }
  scenario_path_override() { :; }
  scenario_expected_divergence() { :; }
  # shellcheck disable=SC1090
  . "$file" || { printf '\n%s\n  ERROR — cannot load scenario\n' "$(basename "${file%.sh}")"; FAIL=$((FAIL+1)); FAILED+=("$(basename "${file%.sh}")"); return; }

  name="$(scenario_name)"
  printf '\n%s  [%s]\n' "$name" "$(scenario_invariants)"

  # A divergence scenario asserts the candidate differs from the reference in a
  # declared way; run reference-vs-reference it can only fail its own "did the
  # divergence actually happen" guard, so it is skipped in the self-check. A
  # scenario whose divergence is toml-lane-only (env-lane clean) still self-
  # checks fine in the env lane, so the gate asks about the env lane.
  if [[ -n "$(scenario_expected_divergence env)" && "$CANDIDATE_IS_REFERENCE" == true ]]; then
    printf '  %-5s unimplemented — divergence scenario needs a real candidate\n' "all"
    UNIMPL=$((UNIMPL+1))
    return
  fi

  for lane in $LANES; do
    if [[ "$lane" == toml && "$CANDIDATE_IS_REFERENCE" == true ]]; then
      printf '  %-5s unimplemented — self-check: the reference has no TOML reader\n' "$lane"
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
