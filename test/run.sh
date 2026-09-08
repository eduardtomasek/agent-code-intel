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
EXTRA_TMP=()   # dirs from mktemp_home(), cleaned up alongside TEST_TMP/TEST_HOME

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

write_code_intel() {  # $1 = adresář, $2.. = řádky souboru .code-intel
  local d="$1"; shift
  printf '%s\n' "$@" > "$d/.code-intel"
}

# Legacy refresh-intel.sh se správným razítkem (sha256 těla sedí), přesně
# jak by ho vygeneroval starý nástroj -- pro testování migrace (#16) bez
# potřeby reálného grepai/gitnexus stacku (script_state() jen parsuje soubor,
# nic nespouští).
write_pristine_refresh_script() {  # $1 = adresář, $2 = WORKSPACE
  local d="$1" ws="$2"
  python3 - "$d/refresh-intel.sh" "$ws" <<'PY'
import hashlib, sys
path, ws = sys.argv[1], sys.argv[2]
lines = [
    "#!/usr/bin/env bash",
    "__STAMP__",
    "#",
    "# refresh-intel.sh -- test fixture",
    "",
    'WORKSPACE="%s"' % ws,
    'PROJECT="whatever"',
    "",
    "echo hi",
]
i = lines.index("__STAMP__")
body = "\n".join(lines[:i] + lines[i + 1:])
h = hashlib.sha256(body.encode()).hexdigest()
lines[i] = "# code-intel-init: version=9.9.9 body=%s" % h
open(path, "w").write("\n".join(lines))
PY
}

# Stejný tvar, ale s razítkem, jehož sha256 neodpovídá tělu -- simuluje ruční
# úpravu po vygenerování, tedy script_state() == modified.
write_modified_refresh_script() {  # $1 = adresář, $2 = WORKSPACE
  local d="$1" ws="$2"
  write_pristine_refresh_script "$d" "$ws"
  printf '\n# a hand-edited line\n' >> "$d/refresh-intel.sh"
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

# --------------------------------------------------------- .code-intel (#12) --
#
# #13 (writing .code-intel in --apply) has no automated test here: --apply
# and --preview both require preflight, which this hermetic harness cannot
# pass without grepai/gitnexus/qdrant/ollama on PATH -- the same known
# limitation #20 already notes for --apply's happy path generally, reserved
# for #16's stub work. Verified manually instead: preview reports CREATE
# without writing; --apply writes the header/SCHEMA=1/WORKSPACE/PROJECT
# shape; a second --apply says "already present" and leaves it byte-for-byte
# unchanged; --status --json afterward reads the workspace back from it.

test_code_intel_overrides_basename() {
  local d; d="$(new_repo 'has-code-intel')"
  write_code_intel "$d" \
    '# needitovat ručně' \
    'SCHEMA=1' \
    'WORKSPACE=nazev-z-souboru' \
    'PROJECT=has-code-intel'
  run "$d" --status
  assert_contains "Workspace: nazev-z-souboru" || return
}

# .code-intel má přednost i nad zaregistrovaným jménem, ne jen nad basename:
# --status --all čte registr, ale projekt s vlastním .code-intel se ohlásí
# pod jménem ze souboru, ne pod (zastaralým) jménem z registru.
test_code_intel_overrides_stale_registry() {
  local d; d="$(new_repo 'registered-project')"
  write_code_intel "$d" 'SCHEMA=1' 'WORKSPACE=aktualni-jmeno' 'PROJECT=registered-project'
  mkdir -p "$TEST_HOME/.config/code-intel"
  printf 'zastarale-jmeno\t%s\n' "$d" >> "$TEST_HOME/.config/code-intel/projects"
  run "$TEST_TMP" --status --all
  assert_contains "aktualni-jmeno" || return
  assert_not_contains "zastarale-jmeno" || return
}

# Explicitní argument na příkazové řádce vyhrává i nad souborem -- to platilo
# už před .code-intel (nad basename) a zůstává to nejvyšší priorita beze změny.
test_code_intel_explicit_arg_still_wins() {
  local d; d="$(new_repo 'has-file-and-arg')"
  write_code_intel "$d" 'SCHEMA=1' 'WORKSPACE=ze-souboru' 'PROJECT=has-file-and-arg'
  run "$d" --status z-prikazove-radky
  assert_contains "Workspace: z-prikazove-radky" || return
}

# --status --all nesmí selhat na projektu, který .code-intel prostě nemá --
# to je běžný, ne chybový stav (ABSENT větev v registrové smyčce).
test_status_all_tolerates_project_without_code_intel() {
  local d; d="$(new_repo 'no-file-registered')"
  mkdir -p "$TEST_HOME/.config/code-intel"
  printf 'stary-nazev\t%s\n' "$d" >> "$TEST_HOME/.config/code-intel/projects"
  run "$TEST_TMP" --status --all
  assert_status 2 || return   # drift je čekaný, žádný jiný stack tu neběží
  assert_contains "stary-nazev" || return
}

test_code_intel_duplicate_key_dies() {
  local d; d="$(new_repo 'duplicate-key-repo')"
  write_code_intel "$d" 'SCHEMA=1' 'WORKSPACE=x' 'WORKSPACE=y' 'PROJECT=duplicate-key-repo'
  run "$d" --status
  [[ "$STATUS" -ne 0 ]] || { fail "duplicitní klíč měl skončit nenulově"; return; }
  assert_contains "duplicate key" || return
}

# Minimální fingovaný `grepai`, jen pro `workspace show`, aby šlo otestovat
# rozpor se skutečným (nebo tady fingovaným) stavem grepai bez závislosti na
# nainstalovaném stacku. Ostatní příkazy stub nezná -- --status nic dalšího
# z grepai nepotřebuje.
stub_grepai() {  # $1 = adresář pro stub, $2 = jméno projektu, $3 = cesta, na kterou je namapován
  local dir="$1" proj="$2" other_path="$3"
  cat > "$dir/grepai" <<STUB
#!/bin/sh
if [ "\$1" = "workspace" ] && [ "\$2" = "show" ]; then
  echo "Workspace: \$3"
  echo "Projects (1):"
  echo "  - $proj: $other_path"
fi
STUB
  chmod +x "$dir/grepai"
}

# Rozpor mezi tím, co grepai skutečně má, a tímto adresářem -- jiná věc než
# "ještě nebylo --apply": jméno je zabrané jinde, --apply samo to nespraví.
# Nepoužívá sdílený run(), protože potřebuje vlastní PATH se stubem.
test_grepai_name_conflict_reports_as_conflict_not_generic_drift() {
  local d stub_dir; d="$(new_repo 'taken-project')"
  stub_dir="$TEST_TMP/stubbin-conflict"; mkdir -p "$stub_dir"
  stub_grepai "$stub_dir" "taken-project" "/somewhere/else"
  OUT="$(env -i HOME="$TEST_HOME" PATH="$stub_dir:$BARE_PATH" TERM=dumb \
        bash -c "cd '$d' && '$TOOL' --status" 2>&1)"
  STATUS=$?
  assert_status 2 || return   # hlášeno jako row, ne die -- --status --all smí pokračovat dál
  assert_contains "CONFLICT" || return
  assert_contains "/somewhere/else" || return
  assert_contains "grepai workspace remove" || return
}

test_code_intel_malformed_line_dies() {
  local d; d="$(new_repo 'malformed-repo')"
  write_code_intel "$d" 'SCHEMA=1' 'workspace=lowercase-key-is-invalid' 'PROJECT=malformed-repo'
  run "$d" --status
  [[ "$STATUS" -ne 0 ]] || { fail "rozbitý .code-intel měl skončit nenulově"; return; }
  assert_contains ".code-intel:2" || return
}

test_code_intel_unknown_key_dies() {
  local d; d="$(new_repo 'unknown-key-repo')"
  write_code_intel "$d" 'SCHEMA=1' 'WORKSPACE=x' 'PROJECT=unknown-key-repo' 'BOGUS=1'
  run "$d" --status
  [[ "$STATUS" -ne 0 ]] || { fail "neznámý klíč měl skončit nenulově"; return; }
  assert_contains ".code-intel:4" || return
  assert_contains "BOGUS" || return
}

test_code_intel_missing_required_key_dies() {
  local d; d="$(new_repo 'missing-key-repo')"
  write_code_intel "$d" 'SCHEMA=1' 'WORKSPACE=x'   # bez PROJECT
  run "$d" --status
  [[ "$STATUS" -ne 0 ]] || { fail "chybějící PROJECT měl skončit nenulově"; return; }
  assert_contains "PROJECT" || return
}

# Rozpor mezi tím, co soubor tvrdí, a skutečným jménem adresáře (typicky po
# přejmenování) — nikdy tichý pád na basename, vždy tvrdá chyba s návodem.
test_code_intel_project_mismatch_dies() {
  local d; d="$(new_repo 'real-dir-name')"
  write_code_intel "$d" 'SCHEMA=1' 'WORKSPACE=x' 'PROJECT=jiny-nazev'
  run "$d" --status
  [[ "$STATUS" -ne 0 ]] || { fail "rozpor PROJECT vs. adresář měl skončit nenulově"; return; }
  assert_contains "jiny-nazev" || return
  assert_contains "real-dir-name" || return
}

test_code_intel_unsupported_schema_dies() {
  local d; d="$(new_repo 'future-schema-repo')"
  write_code_intel "$d" 'SCHEMA=99' 'WORKSPACE=x' 'PROJECT=future-schema-repo'
  run "$d" --status
  [[ "$STATUS" -ne 0 ]] || { fail "nepodporované SCHEMA mělo skončit nenulově"; return; }
  assert_contains "SCHEMA" || return
}

# Rozhodnutí 6 v mapě #2: soubor přichází z cizího klonu, takže se nikdy
# nesmí sourcovat. Vloží se řádek, který by se spuštěním projevil vytvořením
# souboru — a ověří se, že k tomu nedošlo, ať už nástroj skončí jakkoli.
test_code_intel_is_never_sourced() {
  local d marker; d="$(new_repo 'injection-repo')"; marker="$TEST_TMP/pwned-marker"
  rm -f "$marker"
  write_code_intel "$d" "\$(touch $marker)" 'SCHEMA=1' 'WORKSPACE=x' 'PROJECT=injection-repo'
  run "$d" --status
  [[ ! -e "$marker" ]] || { fail ".code-intel byl sourcován -- vznikl $marker"; return; }
}

# Regresní test na opravu z code review: rozbitý .code-intel u jednoho
# registrovaného projektu dřív celý --status --all zabil dřív, než se dostal
# na další řádek registru. Musí se nahlásit jako BROKEN a pokračovat dál.
test_status_all_continues_past_broken_code_intel() {
  local broken healthy
  broken="$(new_repo 'broken-among-many')"
  healthy="$(new_repo 'healthy-among-many')"
  write_code_intel "$broken" 'SCHEMA=1' 'workspace=lowercase-invalid' 'PROJECT=broken-among-many'
  mkdir -p "$TEST_HOME/.config/code-intel"
  printf 'broken\t%s\nhealthy\t%s\n' "$broken" "$healthy" >> "$TEST_HOME/.config/code-intel/projects"
  run "$TEST_TMP" --status --all
  assert_contains "BROKEN" || return
  assert_contains "healthy-among-many" || return
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

# ------------------------------------------------------------------ --refresh --
#
# (#14) Unlike --apply/--preview, a `--refresh --no-grepai --no-gitnexus`
# happy path needs no external stack at all -- both audits are skipped by the
# same flags that skip the writes -- so it is the one full non-error path
# through this mode that this hermetic harness CAN exercise end-to-end.
#
# Exit code 2 (ran, but found drift) is NOT covered here, for the same reason
# noted above for --apply: reaching the audit at all requires refresh_preflight
# to pass, which needs a real grepai+qdrant or gitnexus on PATH. Verified
# manually instead against an already-`--apply`'d project.

test_refresh_never_bootstraps_missing_code_intel() {
  local d; d="$(new_repo 'refresh-no-code-intel')"
  run "$d" --refresh
  assert_status 1 || return
  assert_contains "no .code-intel" || return
  assert_contains "--apply" || return
  local leftover
  leftover="$(cd "$d" && ls -A | grep -v '^\.git$' | grep -v '^file.txt$' || true)"
  [[ -z "$leftover" ]] || { fail "--refresh selhal, ale v repu přibylo: $leftover"; return; }
}

test_refresh_finds_git_root_from_subdirectory() {
  local d; d="$(new_repo 'refresh-nested-root')"
  write_code_intel "$d" 'SCHEMA=1' 'WORKSPACE=root-ws' 'PROJECT=refresh-nested-root'
  mkdir -p "$d/sub/deeper"
  run "$d/sub/deeper" --refresh --no-grepai --no-gitnexus
  assert_status 0 || return
  assert_contains "Workspace: root-ws" || return
}

# Vnořený git repo (např. submodule) musí najít VLASTNÍ .code-intel, ne
# rodičovské -- hranicí hledání kořene je git root (rozhodnutí v #4).
test_refresh_nested_repo_does_not_see_parent_code_intel() {
  local parent; parent="$(new_repo 'refresh-parent-repo')"
  write_code_intel "$parent" 'SCHEMA=1' 'WORKSPACE=parent-ws' 'PROJECT=refresh-parent-repo'
  local child="$parent/child-repo"
  mkdir -p "$child"
  ( cd "$child" && git init -q . )
  write_code_intel "$child" 'SCHEMA=1' 'WORKSPACE=child-ws' 'PROJECT=child-repo'
  run "$child" --refresh --no-grepai --no-gitnexus
  assert_status 0 || return
  assert_contains "Workspace: child-ws" || return
  assert_not_contains "parent-ws" || return
}

# --path je explicitní override: přeskakuje hledání kořene gitu úplně, takže
# ukázaný adresář se bere doslovně, i když leží pod repem s vlastním .code-intel.
test_refresh_path_flag_is_explicit_override() {
  local d; d="$(new_repo 'refresh-path-override')"
  write_code_intel "$d" 'SCHEMA=1' 'WORKSPACE=root-ws' 'PROJECT=refresh-path-override'
  mkdir -p "$d/sub"
  run "$TEST_TMP" --refresh --path "$d/sub"
  assert_status 1 || return
  assert_contains "no .code-intel" || return
}

test_refresh_dies_outside_a_git_repository() {
  mkdir -p "$TEST_TMP/refresh-no-git/plain"
  run "$TEST_TMP/refresh-no-git/plain" --refresh
  assert_status 1 || return
  assert_contains "not inside a git repository" || return
}

test_refresh_preflight_blocks_without_stack() {
  local d; d="$(new_repo 'refresh-preflight-repo')"
  write_code_intel "$d" 'SCHEMA=1' 'WORKSPACE=x' 'PROJECT=refresh-preflight-repo'
  run "$d" --refresh
  assert_status 1 || return
  assert_contains "[ERROR: refresh preflight found" || return
  assert_contains "nothing was refreshed" || return
}

test_refresh_no_grepai_skips_grepai_preflight() {
  local d; d="$(new_repo 'refresh-no-grepai-repo')"
  write_code_intel "$d" 'SCHEMA=1' 'WORKSPACE=x' 'PROJECT=refresh-no-grepai-repo'
  run "$d" --refresh --no-grepai
  assert_status 1 || return           # gitnexus is still missing from bare PATH
  assert_not_contains "grepai not on PATH" || return
  assert_contains "gitnexus not on PATH" || return
}

test_refresh_no_gitnexus_skips_gitnexus_preflight() {
  local d; d="$(new_repo 'refresh-no-gitnexus-repo')"
  write_code_intel "$d" 'SCHEMA=1' 'WORKSPACE=x' 'PROJECT=refresh-no-gitnexus-repo'
  run "$d" --refresh --no-gitnexus
  assert_status 1 || return           # grepai/qdrant is still missing from bare PATH
  assert_not_contains "gitnexus not on PATH" || return
  assert_contains "grepai not on PATH" || return
}

# Když jsou obě strany vypnuté, --refresh nepotřebuje vůbec žádný stack -- to
# je jediná šťastná cesta touto novou funkcí, kterou lze ověřit hermeticky.
test_refresh_with_both_stacks_skipped_needs_no_stack() {
  local d; d="$(new_repo 'refresh-skip-both-repo')"
  write_code_intel "$d" 'SCHEMA=1' 'WORKSPACE=skip-both-ws' 'PROJECT=refresh-skip-both-repo'
  run "$d" --refresh --no-grepai --no-gitnexus
  assert_status 0 || return
  assert_contains "Code intelligence is fresh." || return
}

# ------------------------------------------------ --install permission rule (#15) --
#
# --install writes into ~/.claude/settings.json, which lives under $HOME --
# unlike the rest of the suite, these tests roll their own throwaway HOME
# per test instead of the shared $TEST_HOME: test_suite_does_not_touch_real_home
# asserts $TEST_HOME never gets a settings.json, and these deliberately give
# one to a private, disposable directory instead.

# $TEST_TMP/$TEST_HOME are torn down together by the exit trap below; a home
# made here needs the same guarantee, so it registers itself into EXTRA_TMP
# instead of leaking one throwaway directory per test.
#
# Sets $MKTEMP_HOME rather than echoing the path: `home="$(mktemp_home)"`
# would run this function in a subshell, and EXTRA_TMP+=() there would never
# reach the parent shell's array -- the same reason `run()` below reports
# through the globals $OUT/$STATUS instead of a return value.
mktemp_home() {
  MKTEMP_HOME="$(mktemp -d)"
  EXTRA_TMP+=("$MKTEMP_HOME")
}

run_install() {  # $1 = HOME to install into, $2.. = extra args to --install
  local home="$1"; shift
  OUT="$(env -i HOME="$home" PATH="$BARE_PATH" TERM=dumb "$TOOL" --install "$@" 2>&1)"
  STATUS=$?
}

allow_list() {  # $1 = HOME; echoes permissions.allow as one rule per line
  INSTALL_HOME="$1" python3 -c '
import json, os
p = os.environ["INSTALL_HOME"] + "/.claude/settings.json"
print(chr(10).join(json.load(open(p))["permissions"]["allow"]))
' 2>/dev/null
}

test_install_writes_exact_refresh_rule() {
  mktemp_home; local home="$MKTEMP_HOME"
  run_install "$home"
  assert_status 0 || return
  assert_contains "Bash(agent-code-intel --refresh)" || return
  local allow; allow="$(allow_list "$home")"
  [[ "$allow" == "Bash(agent-code-intel --refresh)" ]] \
    || { fail "allow list není přesně jedno pravidlo bez hvězdičky: $allow"; return; }
}

test_install_removes_legacy_refresh_intel_rules() {
  mktemp_home; local home="$MKTEMP_HOME"
  mkdir -p "$home/.claude"
  cat > "$home/.claude/settings.json" <<'JSON'
{"permissions": {"allow": ["Bash(./refresh-intel.sh)", "Bash(./refresh-intel.sh *)", "Bash(git status)"]}}
JSON
  run_install "$home"
  assert_status 0 || return
  assert_contains "removed legacy" || return
  local allow; allow="$(allow_list "$home")"
  [[ "$allow" == *"refresh-intel.sh"* ]] && { fail "legacy pravidlo přežilo: $allow"; return; }
  [[ "$allow" == *"Bash(agent-code-intel --refresh)"* ]] || { fail "nové pravidlo chybí: $allow"; return; }
  [[ "$allow" == *"Bash(git status)"* ]] || { fail "nesouvisející pravidlo bylo smazáno: $allow"; return; }
}

test_install_no_perms_skips_permission_file() {
  mktemp_home; local home="$MKTEMP_HOME"
  run_install "$home" --no-perms
  assert_status 0 || return
  assert_contains "skipped the Claude Code permission rule" || return
  [[ ! -e "$home/.claude/settings.json" ]] || { fail "--no-perms přesto zapsal settings.json"; return; }
}

test_install_is_idempotent() {
  mktemp_home; local home="$MKTEMP_HOME"
  run_install "$home"
  run_install "$home"
  assert_status 0 || return
  assert_contains "already allowed" || return
  local allow; allow="$(allow_list "$home")"
  [[ "$(printf '%s\n' "$allow" | wc -l | tr -d ' ')" == "1" ]] \
    || { fail "opakovaný --install zdvojil pravidlo: $allow"; return; }
}

test_install_leaves_unreadable_settings_json_untouched() {
  mktemp_home; local home="$MKTEMP_HOME"
  mkdir -p "$home/.claude"
  printf 'not valid json{' > "$home/.claude/settings.json"
  local before; before="$(cat "$home/.claude/settings.json")"
  run_install "$home"
  assert_status 0 || return
  assert_contains "not readable JSON" || return
  assert_contains "Add these to permissions.allow by hand" || return
  local after; after="$(cat "$home/.claude/settings.json")"
  [[ "$before" == "$after" ]] || { fail "nečitelný settings.json byl přesto přepsán"; return; }
}

# --------------------------------------------------- legacy migration (#16) --
#
# The migration itself (do_apply's actual delete-and-write) is NOT covered
# here: it lives entirely behind full preflight, the same known limitation
# already noted above for --apply's happy path generally. What IS reachable
# hermetically: --status's drift reporting around a legacy script (pure file
# reads, no external tool), and --remove, which -- like --status -- runs
# without preflight by design. Verified manually instead against a real,
# in-production refresh-intel.sh: migration adopts its WORKSPACE, deletes it,
# writes .code-intel, strips the stale ignore-list entry and restarts the
# watcher; a hand-edited copy is correctly refused with the exact `rm
# refresh-intel.sh && agent-code-intel --apply` fix command, unchanged.

test_status_no_longer_flags_missing_refresh_script_as_drift() {
  local d; d="$(new_repo 'modern-project')"
  write_code_intel "$d" 'SCHEMA=1' 'WORKSPACE=modern-ws' 'PROJECT=modern-project'
  run "$d" --status
  assert_not_contains "refresh-intel.sh missing" || return
}

test_status_flags_pristine_legacy_script_as_drift() {
  local d; d="$(new_repo 'legacy-project')"
  write_pristine_refresh_script "$d" 'legacy-ws'
  run "$d" --status
  assert_status 2 || return
  assert_contains "refresh-intel.sh present -- run --apply to migrate" || return
}

# Unchanged pre-#16 behavior: a hand-modified script was never flagged by
# --status either (only migration itself refuses it) -- confirms the fix
# above didn't accidentally start (or stop) flagging this case too.
test_status_does_not_flag_modified_legacy_script() {
  local d; d="$(new_repo 'hand-edited-project')"
  write_modified_refresh_script "$d" 'legacy-ws'
  run "$d" --status
  assert_not_contains "refresh-intel.sh present -- run --apply" || return
}

test_remove_deletes_code_intel() {
  local d; d="$(new_repo 'remove-code-intel-repo')"
  write_code_intel "$d" 'SCHEMA=1' 'WORKSPACE=x' 'PROJECT=remove-code-intel-repo'
  run "$d" --remove --apply
  assert_status 0 || return
  assert_contains "removed .code-intel" || return
  [[ ! -e "$d/.code-intel" ]] || { fail ".code-intel přežil --remove --apply"; return; }
}

test_remove_deletes_pristine_legacy_script() {
  local d; d="$(new_repo 'remove-pristine-repo')"
  write_pristine_refresh_script "$d" 'legacy-ws'
  run "$d" --remove --apply
  assert_status 0 || return
  assert_contains "removed refresh-intel.sh" || return
  [[ ! -e "$d/refresh-intel.sh" ]] || { fail "nedotčený legacy skript přežil --remove --apply"; return; }
}

test_remove_leaves_modified_legacy_script_alone() {
  local d; d="$(new_repo 'remove-modified-repo')"
  write_modified_refresh_script "$d" 'legacy-ws'
  run "$d" --remove --apply
  assert_status 0 || return
  assert_contains "hand-modified" || return
  assert_contains "left it alone" || return
  [[ -e "$d/refresh-intel.sh" ]] || { fail "--remove smazal ručně upravený skript"; return; }
}

test_remove_dry_run_changes_nothing() {
  local d; d="$(new_repo 'remove-dry-run-repo')"
  write_code_intel "$d" 'SCHEMA=1' 'WORKSPACE=x' 'PROJECT=remove-dry-run-repo'
  write_pristine_refresh_script "$d" 'legacy-ws'
  run "$d" --remove
  assert_status 2 || return
  assert_contains "rm .code-intel" || return
  assert_contains "rm refresh-intel.sh" || return
  [[ -e "$d/.code-intel" ]]      || { fail "dry-run --remove smazal .code-intel"; return; }
  [[ -e "$d/refresh-intel.sh" ]] || { fail "dry-run --remove smazal refresh-intel.sh"; return; }
}

# A hand-modified script is a "note", not a plannable action, so with
# nothing else to remove this is the "Nothing to remove" exit-0 path -- not
# exit 2 like the pristine case above.
test_remove_dry_run_reports_modified_script_as_note_not_action() {
  local d; d="$(new_repo 'remove-dry-run-modified-repo')"
  write_modified_refresh_script "$d" 'legacy-ws'
  run "$d" --remove
  assert_status 0 || return
  assert_contains "hand-modified" || return
  assert_contains "left alone" || return
  [[ -e "$d/refresh-intel.sh" ]] || { fail "dry-run --remove smazal ručně upravený skript"; return; }
}

# ------------------------------------------------------------------- runner --

TEST_TMP="$(mktemp -d)"; TEST_HOME="$(mktemp -d)"
# Bash 3.2 (macOS): a bare "${EXTRA_TMP[@]}" on an empty array dies with
# "unbound variable" under `set -u` -- guard on the count first.
trap '(( ${#EXTRA_TMP[@]} == 0 )) || rm -rf "${EXTRA_TMP[@]}"; rm -rf "$TEST_TMP" "$TEST_HOME"' EXIT

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
