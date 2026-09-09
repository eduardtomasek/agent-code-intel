# Changelog

Formát vychází z [Keep a Changelog](https://keepachangelog.com/), verzování z
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [4.0.0] - 2026-09-09

Vydání Pythonového přepisu po přepnutí aktivního vstupu, ověření kandidátního
SHA a třech zaznamenaných live relacích.

### Breaking

- CLI v4 vyžaduje Python 3.11 nebo novější a při starším interpretu vrací
  schválenou runtime diagnostiku bez tracebacku.
- Produktová verze má jediný zdroj v `agent_code_intel.__version__`; aktivní
  vstup `agent-code-intel` je Pythonový launcher se stejnou runtime bránou jako
  instalační kopie.

### Přidáno

- Pythonový balík a samostatný launcher pro preview/apply, status, JSON status,
  refresh, remove a instalaci/upgrade.
- Typovaný `defaults.toml` vedle zachované kompatibility s vykonávaným
  `defaults.env`; instalace vytváří TOML šablonu jen při chybějící konfiguraci.
- Bezpečný `--remove` s dry-run plánem, vlastnickými kontrolami a volitelným
  `--purge-collection`.
- Akceptační report s diferenciálními ENV/TOML lanes a versionovaný historický
  audit v `docs/acceptance/`.

### Změněno

- Instalace kopíruje celý vlastní Pythonový balík, zachovává existující
  konfiguraci a podporuje upgrade z v2, v3 i předchozí v4 instalace.
- `--status --json` zachovává smluvené schema; `--refresh` a `--remove`
  zachovávají exit kódy, pořadí účinků a tolerované vzdálené chyby reference.
- README popisuje oba konfigurační formáty, Python 3.11+, ruční přechod a
  oddělené odstranění CLI, konfigurace, projektů a stacku.

### Odstraněno

- Nic nového se neodstraňuje automaticky mimo vlastněné instalační artefakty,
  pristine legacy skript a spravované bloky, které explicitně patří nástroji.

### Testy

- Acceptance report v `docs/acceptance/4.0.0.md` zachycuje referenci, kandidátní
  a finální SHA, hermetické ENV/TOML lanes a tři živé relace na třech repozitářích.
- Report uvádí pouze skutečně provedené důkazy; tři různé pracovní dny ani
  user-session/machine restart nejsou součástí opraveného release scope.

## [3.0.0] - 2026-09-08

Sloučení `refresh-intel.sh` do `agent-code-intel --refresh` — celá wayfinder
mapa [#2](https://github.com/eduardtomasek/agent-code-intel/issues/2), řezy
#11–#20.

### Breaking

- Nástroj přejmenován z `code-intel-init` na `agent-code-intel`. `--install`
  starou binárku v `~/.local/bin/` smaže; žádný compat symlink na staré jméno
  (#11).
- `refresh-intel.sh` se už negeneruje ani nepoužívá. Existující repozitáře se
  zmigrují automaticky při prvním `--apply` po aktualizaci — nedotčená
  vygenerovaná kopie se smaže, ručně upravená se nikdy nesmaže, jen nahlásí a
  ponechá (#16).
- `--force-script` odstraněn (#17).
- `--status --all --json` už nevrací klíč `project.N.script_state` (#17).
- Pravidlo v `~/.claude/settings.json` se změnilo z projektově-relativního
  `Bash(./refresh-intel.sh)` na globální `Bash(agent-code-intel --refresh)`;
  `--install` staré pravidlo automaticky odstraní (#15).

### Přidáno

- Nový režim `--refresh`: přeindexuje GitNexus, nastartuje GrepAI hlídač,
  pokud neběží, a zaudituje oba. Návratové kódy sjednoceny: `0` ok, `1` nešlo
  spustit, `2` drift (#14).
- Soubor `.code-intel` nese identitu repozitáře (`WORKSPACE`, `PROJECT`)
  přímo ve verzovaném repu. `--apply` ho zakládá (#13); nástroj ho čte a
  upřednostňuje před odvozením z `basename` i před registrem (#12).
- Automatická migrace nezmigrovaných repozitářů zabudovaná přímo do `--apply`
  — žádný samostatný přepínač (#16).

### Změněno

- Blok pro AI agenty v `CLAUDE.md`/`AGENTS.md` mluví o chybějícím příkazu
  `agent-code-intel`, ne o selhaném skriptu; plné vysvětlení "proč selhání
  nevadí" se přestěhovalo do `--help` (#18).
- `README.md` kompletně sladěn s novou realitou — nové jméno binárky všude,
  `refresh-intel.sh` nahrazeno `--refresh`, doplněna poznámka o nutném
  přeinstalování `code-intel-dash` (#19).
- `code-intel-dash` (→ 1.1.0): opraven, aby uměl najít přejmenovanou binárku
  — od #11 ji vůbec nedokázal najít, dokud to tenhle řez nespravil — a
  přestal číst zrušený klíč `script_state` (#17).

### Odstraněno

- Generátor `refresh-intel.sh` (`render_refresh()`, ~310řádková šablona)
  (#17).

### Testy

- Sada testů rozšířena z 13 na 53, hermeticky, bez závislosti na skutečném
  stacku. Formálně zdokumentováno, že happy path `--apply` zůstává ověřován
  ručně na živém stacku, ne stuby — přehledně na jednom místě v
  `test/run.sh` (#20).

## [2.4.1] a starší

Historie před tímhle CHANGELOGem nejde z commitů v tomhle repozitáři
dopočítat: nástroj sem přišel v téhle verzi z externího zdroje (viz `git
log`, merge `Hessevalentino/audit-fixes-dashboard-v2.4.1`), ne z vlastního
vývoje v tomhle repu.

[Unreleased]: https://github.com/eduardtomasek/agent-code-intel/compare/52232ad1b202d520474278ca8044e24d7af398d2...HEAD
[4.0.0]: https://github.com/eduardtomasek/agent-code-intel/compare/v3.0.0...52232ad1b202d520474278ca8044e24d7af398d2
[3.0.0]: https://github.com/eduardtomasek/agent-code-intel/releases/tag/v3.0.0
