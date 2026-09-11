# Changelog

Formát vychází z [Keep a Changelog](https://keepachangelog.com/), verzování z
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Změněno

- Minimální verze Node.js je **24.11.0** a bere se z toho, co si žádá GitNexus,
  ne z hádání podle jedné funkce. Preflight dosud testoval přítomnost
  `module.registerHooks`, která přibyla v řadě 22.15 — gitnexus 1.6.11 ale
  deklaruje `engines: ^22.18.0 || >=24.11.0`, takže Node mezi 22.15 a 22.18
  kontrolou prošel, i když ho GitNexus nepodporuje. Z deklarovaného rozsahu
  bereme horní větev jako jedno minimum; je to o něco přísnější, než co GitNexus
  připouští, ale je to jedno číslo místo dvou rozsahů. Hláška teď říká
  `node vX is below the 24.11.0 that gitnexus requires`.
- `--status --json` má u `tool.node` dva nové klíče: `version_ok` (proti čemu se
  rozhoduje) a `version_min`. `register_hooks` zůstává, protože pojmenovává
  přesný projev indexu postaveného pod starým Nodem. `code-intel-dash` svůj
  verdikt bere z `version_ok`.
- README má v kapitole 10 referenční tabulku všech režimů, přepínačů
  a návratových kódů, ověřenou proti `--help`. Včetně toho, že
  `--status --json` vrací nulu i při rozpadu, protože stav se čte z klíče `ok`.
- README uvádí minimum 24.11.0 v přehledu součástí, v seznamu požadavků, v tabulce
  tří úrovní závislostí, v kapitole 7 a v popisu dashboardu.
- `code-intel-dash` ukazuje sekci Stack jako pět řádků pod sebou místo mřížky
  karet. Karty se lámaly podle šířky okna, takže MCP servery na běžném monitoru
  padaly samy na další řádek a stejné údaje byly u každé komponenty jinde —
  kdo hledal, co je špatně, musel číst kartu po kartě. Teď má každá komponenta
  vlevo stav a název, vpravo hodnoty v pěti sloupcích, které lícují napříč
  všemi řádky, a varování s opravou přímo pod nimi; řádek, který potřebuje
  pozornost, má i podbarvené pozadí. Nadpis Stack nese souhrn `all ok`, nebo
  `N of 5 need attention` — MCP bez běžícího serveru se nepočítá, protože je to
  běžný stav. Data, verdikty ani texty varování se nemění. (#108)

## [6.0.0] - 2026-09-10

`.code-intel` si pamatuje, pro které agenty byl projekt zapojený. Hlavní verze
se zvedá kvůli schématu toho souboru, ne kvůli rozsahu změn.

### Breaking

- `--apply` zapisuje `.code-intel` ve **schématu 2** s klíčem `AGENTS`. Starší
  verze nástroje takový soubor odmítnou s hláškou `unsupported SCHEMA=2`, takže
  po downgradu je potřeba `--apply` z té starší verze. Opačný směr je v pořádku:
  soubory se `SCHEMA=1` se čtou dál a fungují beze změny, `--status` u nich jen
  přidá řádek `.code-intel predates AGENTS`, který **není drift** — spuštění
  `--apply` tedy není povinné.

### Přidáno

- `.code-intel` si pamatuje, pro které agenty byl projekt zapojený. `--apply`
  zapisuje `AGENTS=claude|codex|both` a zvedá `SCHEMA` na `2`; `--status`,
  `--refresh` a `--remove` pak pracují právě s těmi agenty, aniž by se jim to
  muselo pokaždé znovu říkat. Dřív byla odpověď jen v příkazové řádce, takže
  projekt zapojený pro samotného Clauda hlásil při každém běhu bez
  `--agent claude` drift na chybějícím Codex routing skillu a chybějícím Codex
  hooku — červená, kterou nešlo uklidit ničím jiným než instalací agenta, který
  uživatele nezajímá. Obcházelo se to wrapperem na `PATH` nebo tím, že se
  přepínač psal ke každému příkazu; obojí je nadbytečné.
- `--status --all` řeší agenty pro každý projekt zvlášť, takže jeden stroj může
  mít vedle sebe projekt pro Clauda i projekt pro oba a každý řádek se porovnává
  s tím, co ten projekt skutečně má.
- JSON ze `--status --all --json` má u každého projektu dva nové klíče: `agents`
  (proti čemu se řádek posuzoval) a `agents_recorded` (co říká jeho vlastní
  soubor, `null` u schématu 1). Ostatní klíče ani jejich pořadí se nemění.

### Změněno

- `--apply` `.code-intel` nejen zakládá, ale i přepisuje, pokud se zaznamenaní
  agenti liší od těch, se kterými se právě spouští — `--agent` je tedy dál
  nadřazený a je to způsob, jak volbu projektu změnit. Identický soubor zůstává
  beze změny bajt po bajtu.
- Hlavička `Agents:` u `--apply`, `--refresh`, `--status` a `--remove` říká i
  odkud hodnota pochází: `(--agent)`, `(from .code-intel)`, nebo `(default)`.

## [5.1.0] - 2026-09-10

Drobné vydání: `--apply` ignoruje `.DS_Store` a preflight pozná BSD `ctags` od
Universal Ctags.

### Opraveno

- Preflight, `--status` a `--install-deps` rozlišují BSD `ctags` od Universal
  Ctags (#99). macOS má `/usr/bin/ctags` vždycky, takže samotná přítomnost nic
  neříkala: stroj bez `universal-ctags` z Homebrew dostával zelené
  `ok ctags on PATH` a `--install-deps` hlásil, že nic nechybí, zatímco příkaz
  předepsaný skillem `code-context` nefungoval vůbec. Nově je to `warn` s
  vlastní příčinou, odlišený od chybějícího `ctags`, a `--install-deps`
  `universal-ctags` skutečně nabídne. `ctags` zůstává doporučený nástroj
  s fallbackem na `ast-grep`, ne povinná závislost.

### Změněno

- `--apply` přidává do `.gitignore` vedle `.grepai/` a `.gitnexus/` i
  `.DS_Store`. Projekty zapojené starší verzí to do prvního `--apply` hlásí
  jako drift `.gitignore += …`; `_ensure_gitignore` přidává jen chybějící
  řádky, takže ručně udržovaný `.gitignore` si zachová své pořadí i obsah.
  Lze to vypnout přes `gitignore_entries` v `defaults.toml`.

### Odstraněno

- `docs/.DS_Store`, commitnutý omylem v `e87a298`.

## [5.0.0] - 2026-09-10

Vydání vlastního code-context řetězce pro Claude a Codex: spravované skilly,
repo-lokální `SessionStart` hooky a kontrola doporučených nástrojů.

### Breaking

- `--apply` nově zapisuje nástrojem vlastněné repo-lokální `SessionStart` hooky
  a druhý skill `code-context`; pro projekty, které si hooky spravují samy,
  je k dispozici `--no-hook`.

### Přidáno

- Samostatný režim `--install-deps`, který kontroluje devět nástrojů a na
  macOS po potvrzení nabídne instalaci dostupných Homebrew balíčků.
- `SessionStart` hook pro Claude i Codex a tři podmínky aktivace Codex hooku
  zdokumentované v README.
- `code-context` jako druhý byte-identický, spravovaný skill pro oba agenty;
  status, refresh a remove rozlišují jeho stav a vlastnictví.

### Změněno

- `ctags` a `rg` jsou v preflightu doporučené nástroje s fallbackem; chybějící
  `ast-grep`, `fd`, `rga`, `tokei` a `scc` se hlásí jako doporučení.
- README uvádí ověřené jazyky, postup pro neověřené jazyky a rozšířené volby
  `--no-hook` a `--no-install-deps`.

### Testy

- 292 unit testů a 53 hermetických black-box scénářů.
- Behaviorální měření code-context řetězce splnilo práh 80 %: tři ze tří
  čtecích operací ve fresh relaci použily odvozený rozsah nebo celý malý
  soubor po ověření jeho velikosti.
- [Acceptance report](docs/acceptance/5.0.0.md) zachycuje živé ověření všech
  projektových režimů pro `claude`, `codex` i `both` na čistých projektech a
  samostatnou kontrolu `--install-deps`.

- README přepsán na kratší podobu: zkrácený titul, sjednocené číslování obsahu
  a nový hero obrázek (`hero.jpg`).

### Odstraněno

- Zmrazený Bash reference harness, diferenční scénáře a jeho shellové helpery.
  Aktivní Pythonová testovací sada zůstává; fixture pro podporovanou migraci
  existujících `refresh-intel.sh` projektů je nyní malý Pythonový pomocník.
- Sdílený `test/lib/isolated_path.sh` resolver interpretu; `test/unit.sh` teď
  bere Python 3.11 přímo a `ACI_PYTHON` volí doplňkový interpret explicitně.

### Opraveno

- `.code-intel` s mezerou v hodnotě je nyní čitelný zpět. `--apply` zapisuje
  `PROJECT` jako holý basename adresáře bez uvozovek, ale `_LINE_RE` vyžadovalo
  `\S+`, takže projekt v adresáři jako `CS Imager (test)` skončil při každém
  dalším `--status` a `--refresh` chybou `malformed line`. Hodnota se rozšířila
  na `.+`; validace klíčů (malé písmeno, řádek bez `=`, prázdná hodnota) se
  nemění.

## [4.1.0] - 2026-09-09

Vydání spravovaného routing skillu pro GrepAI, GitNexus a volitelný ripgrep,
včetně bezpečné distribuce pro Claude a Codex.

### Přidáno

- `agent-code-intel-routing`: byte-identický spravovaný skill v
  `.claude/skills/` pro Claude a `.agents/skills/` pro Codex; `--agent
  claude|codex|both` určuje, které kopie se při `--apply` vytvoří.
- Kontrola skillu ve `--status`, `--status --json` a `--refresh`; `--remove`
  odstraňuje pouze nástrojem vlastněné kopie a `.agents` se neindexuje GrepAI.
- README s rychlým startem od závislostí po `--apply`, návodem na aktualizaci a
  volitelným `ripgrep` (`rg`) pro přesné hledání a ověření.

### Změněno

- `--install` nově instaluje i `code-intel-dash`; jeho vlastní `VERSION` řídí
  aktualizaci dashboardu nezávisle na verzi `agent-code-intel`.
- Běžný `--apply` je pro spravovaný skill idempotentní: byte-identický soubor
  nemění a drift nástrojem vlastněného souboru opraví atomicky.

### Odstraněno

- Serena z instrukcí nového routing skillu; rozhodování nyní používá GrepAI
  pro význam, GitNexus pro vztahy a `rg` pro přesné dotazy a ověření.

### Testy

- 260 unit testů a 53 hermetických black-box scénářů pokrývá lifecycle skillu,
  volbu agenta, idempotenci, drift, instalaci, status, refresh a remove.

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

[Unreleased]: https://github.com/eduardtomasek/agent-code-intel/compare/v6.0.0...HEAD
[6.0.0]: https://github.com/eduardtomasek/agent-code-intel/compare/v5.1.0...v6.0.0
[5.1.0]: https://github.com/eduardtomasek/agent-code-intel/compare/v5.0.0...v5.1.0
[5.0.0]: https://github.com/eduardtomasek/agent-code-intel/compare/v4.1.0...v5.0.0
[4.1.0]: https://github.com/eduardtomasek/agent-code-intel/compare/v4.0.0...v4.1.0
[4.0.0]: https://github.com/eduardtomasek/agent-code-intel/compare/v3.0.0...v4.0.0
[3.0.0]: https://github.com/eduardtomasek/agent-code-intel/releases/tag/v3.0.0
