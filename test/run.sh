#!/usr/bin/env bash
# test/run.sh — black-box testy pro agent-code-intel.
#
# Proč černá skříňka: skript nemá source guard (parsuje argumenty a dispatchuje
# na nejvyšší úrovni), takže se z něj nedají volat jednotlivé funkce, aniž by se
# rozběhl celý. Testovat přes CLI je tedy jediná cesta, která nevyžaduje jeho
# přestavbu — a zároveň připíná přesně to, co musí refactor přežít: návratové
# kódy, texty chyb a to, že se v případě selhání nic nezmění.
#
# Hermetičnost: každý test běží pod `env -i` s vlastním HOME a s
# PATH=/usr/bin:/bin. Ten obsahuje python3, git a curl, ale NE grepai, gitnexus,
# ollama, node, claude ani codex — je to tedy věrný model stroje, kde stack
# není nainstalovaný. Skutečný ~/.claude ani ~/.config se nikdy nedotkne.
#
# Spuštění:  ./test/run.sh
# Jeden test: ./test/run.sh workspace_derived_from_basename

set -uo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TOOL="${TOOL:-$HERE/../agent-code-intel}"
EXPECTED_NAME="${EXPECTED_NAME:-agent-code-intel}"

BARE_PATH=/usr/bin:/bin

PASS=0; FAIL=0; FAILED_NAMES=()

# ------------------------------------------------------------------ helpers --

# run <workdir> <args...> — spustí nástroj hermeticky, uloží stdout+stderr do
# $OUT a návratový kód do $STATUS.
run() {
  local wd="$1"; shift
  OUT="$(env -i HOME="$TEST_HOME" PATH="$BARE_PATH" TERM=dumb \
        bash -c "cd '$wd' && '$TOOL' $*" 2>&1)"
  STATUS=$?
}

new_repo() {  # $1 = jméno adresáře; echoes cestu
  local d="$TEST_TMP/$1"
  mkdir -p "$d"
  ( cd "$d" && git init -q . && printf 'x\n' > file.txt )
  printf '%s\n' "$d"
}

fail() { FAIL=$((FAIL+1)); FAILED_NAMES+=("$CURRENT"); printf '  FAIL  %s\n        %s\n' "$CURRENT" "$1"; }

assert_status() {
  [[ "$STATUS" == "$1" ]] || { fail "čekal exit $1, dostal $STATUS. Výstup:
$(printf '%s' "$OUT" | sed 's/^/        | /' | head -15)"; return 1; }
}
assert_contains() {
  [[ "$OUT" == *"$1"* ]] || { fail "výstup neobsahuje: $1. Výstup:
$(printf '%s' "$OUT" | sed 's/^/        | /' | head -15)"; return 1; }
}
assert_not_contains() {
  [[ "$OUT" != *"$1"* ]] || { fail "výstup neměl obsahovat: $1"; return 1; }
}

# --------------------------------------------------------------------- testy --

test_version_prints_name_and_version() {
  run "$TEST_TMP" --version
  assert_status 0 || return
  assert_contains "$EXPECTED_NAME " || return
  [[ "$OUT" =~ [0-9]+\.[0-9]+\.[0-9]+ ]] || { fail "verze nevypadá jako semver: $OUT"; return; }
}

test_help_exits_zero_and_lists_modes() {
  run "$TEST_TMP" --help
  assert_status 0 || return
  local m
  for m in --status --remove --install --apply; do
    assert_contains "$m" || return
  done
}

test_unknown_flag_is_rejected() {
  run "$TEST_TMP" --definitely-not-a-flag
  [[ "$STATUS" -ne 0 ]] || { fail "neznámý flag měl skončit nenulově"; return; }
  assert_contains "unknown flag" || return
}

test_bad_agent_value_is_rejected() {
  run "$TEST_TMP" --agent nope
  [[ "$STATUS" -ne 0 ]] || { fail "špatná hodnota --agent měla skončit nenulově"; return; }
  assert_contains "--agent must be claude, codex or both" || return
}

test_workspace_given_twice_is_rejected() {
  run "$TEST_TMP" foo bar
  [[ "$STATUS" -ne 0 ]] || { fail "dvě jména workspace měla skončit nenulově"; return; }
  assert_contains "workspace name given twice" || return
}

# Slugifikace jména adresáře na jméno workspace: malá písmena, nealfanumerické
# znaky na pomlčku, sloučené a oříznuté pomlčky.
test_workspace_derived_from_basename() {
  local d; d="$(new_repo 'My.Project_X')"
  run "$d" --status
  assert_contains "Workspace: my-project-x" || return
}

test_explicit_workspace_argument_wins() {
  local d; d="$(new_repo 'some-repo')"
  run "$d" --status vlastni-jmeno
  assert_contains "Workspace: vlastni-jmeno" || return
}

# Nástroj cestu kanonizuje přes getcwd() (funkce `canon`), takže na macOS
# vrací /private/var/... i pro /var/... — porovnává se proto kanonická cesta.
test_path_flag_overrides_cwd() {
  local d canon; d="$(new_repo 'elsewhere')"
  canon="$(cd "$d" && /bin/pwd -P)"
  run "$TEST_TMP" --status --path "$d"
  assert_contains "Project:   $canon" || return
}

# --status a --remove musí jít spustit na stroji, kde služby neběží: člověk musí
# být schopen projekt prohlédnout a rozebrat i bez stacku. Proto tyhle režimy
# záměrně nespouštějí plný preflight.
test_status_runs_without_the_stack() {
  local d; d="$(new_repo 'no-stack')"
  run "$d" --status
  assert_status 2 || return              # 2 = proběhlo, ale našlo drift
  assert_contains "code-intel status" || return
  assert_not_contains "preflight" || return
}

test_status_json_is_valid_and_has_schema() {
  local d; d="$(new_repo 'json-repo')"
  run "$d" --status --json
  assert_status 0 || return
  printf '%s' "$OUT" | python3 -c '
import json,sys
d = json.load(sys.stdin)
assert d["meta"]["schema"] == "1", "meta.schema != 1"
assert "tool" in d, "chybí klíč tool"
' 2>/dev/null || { fail "výstup není platný JSON s meta.schema=1"; return; }
}

# Dokumentovaný kontrakt: bez závislostí se nic neindexuje ani nemění.
test_preflight_blocks_init_without_stack() {
  local d; d="$(new_repo 'preflight-repo')"
  run "$d"
  assert_status 1 || return
  assert_contains "[ERROR: preflight found" || return
  assert_contains "nothing was changed" || return
}

test_failed_preflight_leaves_repo_untouched() {
  local d; d="$(new_repo 'untouched-repo')"
  run "$d"
  local leftover
  leftover="$(cd "$d" && ls -A | grep -v '^\.git$' | grep -v '^file.txt$' || true)"
  [[ -z "$leftover" ]] || { fail "preflight selhal, ale v repu přibylo: $leftover"; return; }
}

# Pojistka proti tomu, aby testy sahaly na skutečnou konfiguraci uživatele.
test_suite_does_not_touch_real_home() {
  local d; d="$(new_repo 'isolation-repo')"
  run "$d" --status --json
  [[ ! -e "$TEST_HOME/.claude/settings.json" ]] || { fail "test zapsal do settings.json"; return; }
  # meta.config_file musí ukazovat do izolovaného HOME, ne do skutečného.
  printf '%s' "$OUT" | TEST_HOME="$TEST_HOME" python3 -c '
import json,os,sys
cf = json.load(sys.stdin)["meta"]["config_file"]
home = os.environ["TEST_HOME"]
assert cf.startswith(home), "config_file mimo izolovaný HOME: %s" % cf
' 2>/dev/null || { fail "nástroj nečte konfiguraci z izolovaného HOME"; return; }
}

# ------------------------------------------------------------------- runner --

TEST_TMP="$(mktemp -d)"; TEST_HOME="$(mktemp -d)"
trap 'rm -rf "$TEST_TMP" "$TEST_HOME"' EXIT

[[ -x "$TOOL" ]] || { echo "[ERROR: nástroj není spustitelný: $TOOL]" >&2; exit 1; }

# bez `mapfile`: macOS má ve výchozím stavu bash 3.2, kde neexistuje.
ALL=()
while IFS= read -r fn; do ALL+=("$fn"); done < <(declare -F | awk '{print $3}' | grep '^test_' | sort)
if [[ $# -gt 0 ]]; then
  SELECTED=(); for a in "$@"; do SELECTED+=("test_${a#test_}"); done
else
  SELECTED=("${ALL[@]}")
fi

printf 'nástroj: %s\n\n' "$TOOL"
for t in "${SELECTED[@]}"; do
  if ! declare -F "$t" >/dev/null; then echo "  ?     neznámý test: $t"; FAIL=$((FAIL+1)); continue; fi
  CURRENT="${t#test_}"
  before=$FAIL
  "$t"
  if [[ $FAIL == "$before" ]]; then PASS=$((PASS+1)); printf '  ok    %s\n' "$CURRENT"; fi
done

printf '\n%d prošlo, %d selhalo\n' "$PASS" "$FAIL"
if (( FAIL > 0 )); then printf 'selhalo: %s\n' "${FAILED_NAMES[*]}"; exit 1; fi
