# Audit code-intel-init

**Ověření před nasazením · 7. září 2026**

Prostudování návodu, statická analýza skriptu a 255 reálných testů proti
běžícímu qdrantu a ollamě. Tři nálezy ve skriptu, šest oprav v návodu, všechno
ověřené měřením.

| | |
|---|---|
| **Auditovaný skript** | `code-intel-init` v2.4.0 → opraveno na v2.4.1, 1847 řádků bash |
| **Stroj** | macOS 25.6 (arm64), bash 3.2.57 |
| **Stack** | grepai 0.36.1 · gitnexus 1.6.11 · qdrant přes OrbStack · ollama s `nomic-embed-text-v2-moe` |

---

## Závěr

**Skript je funkční a k nasazení připravený.** Jádro dělá přesně to, co slibuje:
sémantické vyhledávání našlo správný soubor i na český dotaz bez jediného
společného slova s kódem, hlídač zaindexoval nový soubor za 2 sekundy a klíčová
„drahá znalost" v hlavičce — že výchozí chunk 512 tiše shazuje celé soubory
z indexu — se potvrdila měřením.

Našel jsem tři chyby. Jedna je uživatelsky citelná: příkaz, který návod
doporučuje pro kontrolu všech projektů, spadl, pokud se spustil z domovského
adresáře. Žádná z nich nepoškozovala data ani cizí konfiguraci. Všechny tři jsou
opravené a opravy ověřené.

| | Před opravou | Po opravě |
|---|---:|---:|
| Testy | 234 / 235 | **255 / 255** |
| shellcheck (errors + warnings) | 0 | 0 |
| Nálezy | 3 | 0 |

---

## Nálezy ve skriptu

### F1 — `--status --all` spadl, když se spustil z domovského adresáře

**Závažnost: střední**

Pojistky proti spuštění nad `$HOME` běžely ve fázi rozlišení cest, tedy *dřív*
než se rozhodlo o režimu. Jenže `--status --all` čte registr projektů a na
`$PWD` se vůbec nedívá — pojistka tu nechránila před ničím a jen blokovala.
Návod tenhle příkaz uvádí v kapitole 13 bez pokynu někam přejít, a to přesně pro
situaci po restartu Macu, kdy terminál startuje v domovském adresáři.

Hláška navíc mířila jinam, než byl problém: radila „point `--path` at a single
project", ačkoli `--all` žádný jednotlivý projekt neřeší.

**Reprodukce**

```
cd ~ && code-intel-init --status --all
[ERROR: refusing to run over your home directory (/Users/…) — point --path at a single project]
rc=1
```

**Oprava** — trojice pojistek je obalená podmínkou:

```bash
if [[ "$MODE" != "status" || "$STATUS_ALL" != true ]]; then
  HOME_REAL="$(canon "$HOME")"
  [[ "$ROOT" != "$HOME_REAL" ]] || die "refusing to run over your home directory …"
  [[ "$ROOT" != "/" ]]          || die "refusing to run over the filesystem root"
  [[ "$HOME_REAL" != "$ROOT"/* ]] || die "refusing to run over $ROOT: it contains …"
fi
```

Zápisové režimy (`init`, `remove`) i obyčejný `--status` je mají dál — ověřeno
čtyřmi regresními testy, včetně `--apply` nad `/`.

---

### F2 — pod `--agent claude` skončil blok instrukcí i v `AGENTS.md`

**Závažnost: nízká**

Krok 6 spouští `gitnexus analyze`, a ten si **sám zapisuje vlastní `AGENTS.md` a
`CLAUDE.md`** (v značkách `<!-- gitnexus:start -->`) plus šest skill souborů do
`.claude/skills/`. Krok 8 pak adoptoval každý `AGENTS.md`, který „už v projektu
je" — jenže o dva kroky dřív ho vyrobil tenhle samý běh. Test
`-f "$ROOT/AGENTS.md"` to nerozliší.

Důsledek: uživatel bez Codexu dostal do repozitáře `AGENTS.md` s duplicitními
instrukcemi.

**Oprava** — nový predikát rozliší soubor, který si projekt skutečně vede, od
toho, který právě vyrobil GitNexus:

```bash
agents_md_project_owned() {
  [[ -f "$ROOT/AGENTS.md" ]] || return 1
  python3 - "$ROOT/AGENTS.md" <<'AGENTSPY'
import re, sys
s = open(sys.argv[1], errors="replace").read()
s = re.sub(r'<!-- gitnexus:start -->.*?<!-- gitnexus:end -->', '', s, flags=re.S)
sys.exit(0 if s.strip() else 1)
AGENTSPY
}
```

Použit v `do_preview` i `do_apply`. Snapshot stavu před krokem 6 by nestačil —
při druhém `--apply` už soubor existuje od začátku a selhalo by to znovu; to se
při ověřování skutečně stalo a oprava se musela předělat.

**Ověřeno:** blok se nepřidá pod `--agent claude` ani při opakovaném běhu; do
`AGENTS.md`, který si projekt skutečně vede, se přidá dál a jeho původní obsah
zůstane.

---

### F3 — stack indexoval sám sebe, 90 z 96 vektorů bylo vlastní lešení

**Závažnost: nízká**

Ignore list řešil lock soubory, ale ne soubory, které stack vyrobí sám. Na
pětisouborovém projektu vypadala kolekce takto:

| Obsah | Vektorů |
|---|---:|
| `.claude/skills/` — šest skill souborů od GitNexusu | 56 |
| `refresh-intel.sh` | 15 |
| `AGENTS.md` + `CLAUDE.md` | 16 |
| `.mcp.json` | 2 |
| **reálný kód** (`auth.js`, `db.js`, `server.js`) | **6** |
| **celkem** | **96** |

Na dotazy na kód se správné soubory držely na 1.–4. místě, takže o chybu nešlo;
šlo o plýtvání embeddingem a ředění indexu, který má tyhle nástroje dělat
užitečnými. Šum se přesto objevil už na 5. pozici při dotazu *„how do I look up
a user record"*.

**Oprava** — do `EXTRA_IGNORES` přibylo `.claude`, `refresh-intel.sh` a
`.mcp.json`. Doc bloky jsou ponechané záměrně: jsou to legitimní instrukce,
které agent může chtít prohledat.

**Dopad:** kolekce klesla z 96 na 21 vektorů, podíl reálného kódu z 6 % na 33 %.

---

## Klíčové měření: chunk 512 opravdu tiše shazuje soubory

Hlavička skriptu tvrdí, že výchozí `chunking.size` od GrepAI přeteče
512‑tokenové okno modelu `nomic-embed-text-v2-moe` a soubory se do indexu nikdy
nedostanou. Zaindexoval jsem tytéž soubory dvakrát:

| Soubor | 256/25 — nastavení skriptu | 512/50 — výchozí GrepAI |
|---|---|---|
| `auth.js` | ✅ 2 chunky | ✅ 2 chunky |
| `db.js` | ✅ 2 | ✅ 1 |
| `server.js` | ✅ 2 | ✅ 2 |
| `small.js` | ✅ 2 | ✅ 2 |
| `medium.js` | ✅ 12 | ❌ **chybí** |
| `large.js` | ✅ 55 | ❌ **chybí** |
| **celkem vektorů** | **92** | **9** |

Dva ze šesti souborů zmizely beze stopy — bez chyby, bez záznamu, jen prostě
nejsou v indexu. Tohle je jednoznačně nejcennější věc, kterou skript dělá.

---

## Co drží — ověřená tvrzení

- **Sémantické hledání funguje i česky.** Dotaz „overeni hesla uzivatele" vrátil
  jako první `auth.js`, kde není ani slovo „ověření", ani „heslo". Obyčejný grep
  by nenašel nic.
- **Hlídač indexuje průběžně.** Nový `billing.js` byl v qdrantu za 2 sekundy
  a hned dohledatelný dotazem „spocitej mesicni fakturu vcetne dane".
- **`canon()` řeší case‑insensitive cesty správně.** Pro `~/Projects`
  i `~/projects` vrací skutečné jméno na disku — což pythonový
  `os.path.realpath` na témž stroji nedokáže.
- **Zápis do cizí konfigurace je bezpečný.** Sedm nepřátelských variant
  `~/.claude/settings.json` (rozbitý JSON, pole místo objektu, `allow` špatného
  typu, nulová délka): merge zachoval `model`, `env` i `deny`, a co nešlo
  přečíst, nechal bajt po bajtu být.
- **Idempotence platí.** Opakovaný `--apply` nezdvojil doc blok, řádek
  v `.gitignore` ani záznam v registru; preview pak konverguje na exit 0.
- **Odinstalace nesní uživatelův obsah.** Vlastní text v `CLAUDE.md` přežil, kód
  i git zůstaly nedotčené — a `CLAUDE.md`, které obsahovalo jen blok, se smazalo
  místo prázdného pahýlu.
- **Chybové cesty dávají funkční rady.** U konfliktu jmen skript vypsal
  `grepai workspace remove …`; ten příkaz jsem spustil a projekt se pak zapojil
  napoprvé.
- **Generovaný `refresh-intel.sh` obstojí i sám.** Je shellcheck‑čistý, na stroji
  bez stacku skončí s exit 1 a vysvětlí, že to o zdraví projektu nic neříká.
  Stavový automat missing / current / outdated / modified funguje včetně respektu
  k ruční úpravě.
- **Diagnostika staré Node.js je vzorná.** Stroj měl Node 22.14.0 bez
  `registerHooks`. Skript to zachytil v preflightu, znovu u kroku 6 a potřetí
  v závěrečném shrnutí — a běh nepřerušil, takže zbytek se zapojil.
- **Hraniční případy `.gitignore`.** Sedm variant včetně souboru bez koncového
  řádku: žádné slepené řádky, žádné utnutí běhu přes `set -e`.

---

## Opravy v návodu

Šest míst, kde návod neodpovídal realitě. Všechna jsou v `navod.md` opravená.

| Kap. | Co bylo | Co je teď |
|---|---|---|
| úvod | `code-intel-init --apply` | `--agent claude --apply` + vysvětlení. Výchozí `--agent` je `both`, takže úvodní slib bez Codexu selhal. |
| 7 | `brew upgrade node` pro `/opt/homebrew` i `/usr/local` | Tři odlišené případy. Node z instalátoru z nodejs.org (`/usr/local/bin`, Homebrew o něm neví) vrací `Error: node not installed` — tam se používá `brew install node`. Tenhle případ byl i na testovaném stroji. |
| 11 | Tabulka šesti vytvořených souborů | Devět řádků se sloupcem „kdo ho vytvoří". Doplněno `.gitnexus/`, `AGENTS.md` a `.claude/skills/` — všechno dělá `gitnexus analyze`. Přidána poznámka, že `.claude/` není v `.gitignore`. |
| 12 | „Ten commit není formalita — GitNexus … bez commitu to nedokáže vyhodnotit" | Na gitnexus 1.6.11 už neplatí: `analyze` v repozitáři bez jediného commitu a `status` hlásí `up-to-date`. Commit je teď doporučený, ne podmínka. |
| 12 | `code .` bez alternativy | Doplněna varianta pro `command not found` a vytvoření souboru přes heredoc. |
| 14 | `brew upgrade node` podruhé | Odkaz na tři případy z kapitoly 7. |

Kapitola 13 (`code-intel-init --status --all`) zůstala beze změny — po opravě F1
příkaz funguje odkudkoli, jak návod předpokládal.

---

## Testy

Devět sad, celkem 255 tvrzení. Každá sada běží v izolovaném `HOME`, takže se
skutečná konfigurace nemohla znečistit, ale proti *reálnému* qdrantu a ollamě —
žádné mocky. Sady t3–t9 zakládaly skutečné workspace, indexovaly skutečné
vektory a spouštěly skutečný `gitnexus analyze`.

| Sada | Co ověřuje | v2.4.0 | v2.4.1 |
|---|---|---:|---:|
| `t1-cli` | parsování argumentů, pojistky, odvození jména workspace | 33 | 33 |
| `t2-install` | `--install` a merge do `~/.claude/settings.json` | 26 | 26 |
| `t3-e2e` | celý životní cyklus, idempotence, konvergence preview | 37 **+1 fail** | 38 |
| `t4-chunking` | měření ztráty souborů při chunku 512 | 1 | 1 |
| `t5-refresh` | `refresh-intel.sh`: stamp, stavy, `--audit`, holý stroj | 31 | 31 |
| `t6-remove-status` | `--remove`, `--status`, doc bloky, rozbité značky | 40 | 40 |
| `t7-conflicts` | konflikt jmen, nesoulad embedderu, `defaults.env` | 31 | 31 |
| `t8-gitignore` | hraniční případy zápisu (chybějící koncový řádek, `set -e`) | 35 | 35 |
| `t9-fixes` | reprodukce F1–F3 a regrese oprav | — | 20 |
| **celkem** | | **234 / 1** | **255 / 0** |

**Statická analýza:** `shellcheck` na 1847 řádcích hlásí nula errors a nula
warnings, jen dva kosmetické nity `SC2004` na řádku 724. Na skript téhle
velikosti je to nadprůměrné. Generovaný `refresh-intel.sh` je čistý také.

Testovací sady jsem po dokončení auditu smazal podle zadání; report zůstává
jediným záznamem. Kdyby byly potřeba znovu, jde o standardní bash harness
s izolovaným `HOME` a asserty proti exit kódům a výstupu.

---

## Stav stroje

Testy běžely v izolovaném `HOME`; uživatelská konfigurace se nezměnila. Ověřeno
diffem proti záloze:

```
UNCHANGED  ~/.grepai/workspace.yaml
UNCHANGED  ~/.claude/settings.json
UNCHANGED  ~/.config/code-intel/projects
UNCHANGED  ~/.config/code-intel/defaults.env
~/.claude.json — změněny jen telemetrické klíče Claude Code
                 (skillUsage, tipsHistory); mcpServers bit po bitu shodné
```

Testovací workspaces i qdrant kolekce jsou smazané, testovací hlídače ukončené.
Zůstal jen vlastní `workspace_test-intel` a jeho watcher.

### Čtyři záměrné změny na stroji

Bez nich se polovina stacku otestovat nedala:

- **`brew install node` → 26.8.1** v `/opt/homebrew/bin`. Původní 22.14.0
  v `/usr/local/bin` je netknutý, jen ho nová verze v PATH zastiňuje. **Tím se
  opravil `gitnexus analyze`**, který do té chvíle padal na `registerHooks`.
- **`npm i -g gitnexus` → 1.6.11** (bylo 1.6.9), povinná přeinstalace po změně
  Node.
- **`brew install shellcheck`** pro statickou analýzu.
- Spuštěn **OrbStack** a kontejner `grepai-qdrant`; oba porty publikuje správně.

### Dvě věci k vyřešení

- Na `PATH` je stále **code-intel-init v2.3.0** z `~/.local/bin`, zatímco tady
  leží v2.4.1. Přeinstalace:

  ```
  cd ~/Downloads/INTELCODE && ./code-intel-init --install
  ```

- Registr obsahuje **dva řádky pro tentýž adresář** (`~/Projects/test-intel`
  a `~/projects/test-intel`). `registry_del` porovnává cesty jako řetězce, takže
  se case‑varianty nesloučí. Ruční oprava:

  ```
  grep -v '/Projects/' ~/.config/code-intel/projects > /tmp/p && mv /tmp/p ~/.config/code-intel/projects
  ```

  Existující projekt `~/projects/test-intel` navíc hlásí drift ve dvou bodech:
  `refresh-intel.sh` je od starší verze generátoru a v ignore listu chybí lock
  soubory (ten se rozšířil opravou F3). Oboje spraví jeden běh:

  ```
  cd ~/projects/test-intel && code-intel-init --agent claude --apply
  ```

Kosmetická drobnost, kterou jsem nechal být: `--status --all` vypisuje
v hlavičce `Workspace:` jméno odvozené z aktuálního adresáře, přestože v tomhle
režimu nic neznamená. Z domovského adresáře to vypadá jako `Workspace:
valentinohesse`. Na funkci to nemá vliv.

---

## Co je ve složce

| Soubor | Obsah |
|---|---|
| `code-intel-init` | **v2.4.1** — opravy F1–F3 a režim `--status --all --json` |
| `code-intel-dash` | **v1.0.0** — lokální dashboard, bez závislostí |
| `navod.md` | návod se šesti opravami a novou kapitolou 14 |
| `report.md` | tento dokument |

Změny ve skriptu proti dodané v2.4.0: tři opravy, bump verze, čtyři odstavce
v hlavičkovém bloku „knowledge that is expensive to rediscover" a přírůstek
`--json` popsaný níže.

---

## Dashboard

Přidán na vyžádání po dokončení auditu, jako odpověď na otázku „běží všechno
a dělá to, co má". Audit totiž odhalil, že na ni dosud nešlo odpovědět:

```
status_one()  kontroluje  workspace, mapování, embedder, chunking,
                          ignore list, watcher, verzi refresh-intel.sh
zmínek o qdrant/ollama/docker ve status větvi:  0
```

Service probes ve skriptu existovaly, ale volaly se jen z `preflight()` — tedy
pouze v init režimu, a preflight služby rovnou *startuje*. Neexistoval příkaz,
který beze změn odpoví na otázku po zdraví stacku.

### Architektura

Dashboard **nemá vlastní probes**. To je jeho hlavní návrhové rozhodnutí a plyne
přímo z hlavičky auditovaného skriptu:

> One implementation per question. Preview, apply, status and remove all call
> these, so they can never disagree with each other.

Druhá implementace otázky „běží hlídač?" by se s bashovou rozešla — a rozešla by
se tiše, protože obě by dál svítily zeleně. Proto:

1. **`code-intel-init --status --all --json`** (nový režim, ~110 řádků) staví
   nad *existujícími* probes JSON dokument se službami i projekty. Nic nestartuje
   — na rozdíl od preflightu jen hlásí.
2. **`code-intel-dash`** je tenká slupka nad tím příkazem. Přidává jen to, co je
   monitorovací, ne rekonciliační: živé funkční testy, uložené statistiky a logy.

### Liveness versus correctness

Klíčový požadavek nebyl „běží/neběží", ale „dělá to, co má". Každá komponenta
proto dostane test toho, kvůli čemu existuje:

| Komponenta | Funkční test |
|---|---|
| ollama | pošle skutečný text k embedování, spočítá dimenze, změří latenci |
| qdrant | počet vektorů v kolekci — zelená kolekce s nulou je rozbitý index |
| GrepAI | spustí skutečný dotaz; nula výsledků = prázdný index, ne špatný dotaz |
| GitNexus | z `meta.json` uzly, hrany, indexovaný commit vs HEAD — a **verzi Node, pod kterou byl index postavený** |
| hlídač | tail logu; běžící hlídač bez aktivity v logu je tichá zastaralost |

Ten předposlední řádek je nejcennější: `meta.json` nese
`runnerIdentity.runtime.version`, takže dashboard pozná index postavený pod
starým Node — přesně past, kvůli které vznikl nález v kapitole o Node.js.

### Ověření

Naměřeno na reálném stacku:

| | |
|---|---|
| sběr celého reportu | 0,9–1,3 s |
| test embeddingu | 768 dimenzí / 107 ms |
| testovací dotaz GrepAI | 10 výsledků / 134 ms |
| vazba | `127.0.0.1` pouze (ověřeno `lsof`) |

Injektované poruchy a jejich detekce:

| Porucha | Výsledek |
|---|---|
| zastavený hlídač | projekt červeně, „hlídač NEBĚŽÍ", dotaz přeskočen, vypsán opravný příkaz, `rc=2` |
| zastavený qdrant | kontejner `exited`, HTTP i gRPC červeně, ollama a GitNexus **správně zůstaly zelené** |
| obojí obnoveno | `rc=0` |

Poslední řádek je důležitý: výpadek jedné komponenty nesmí obarvit načerveno
komponenty, kterých se netýká, jinak se hledání příčiny prodlouží.

Stránka se obnovuje po 15 s a když odečet zestárne nad 25 s, **zešedne a napíše,
že za nic neručí** — dashboard, který po výpadku dál ukazuje poslední zelený
obrázek, je horší než žádný.

### Regrese po přidání `--json`

Testovací sada byla podle dřívějšího zadání smazána, takže těch 255 testů už
nešlo spustit. Změna je aditivní (nový flag, nová funkce, dvě podmínky), ověřena
cílenou regresí **20/20**: exit kódy, obě pojistky nad `$HOME` a `/`, zachovaná
preambule v běžných režimech, celý cyklus preview → apply → konvergence →
refresh → remove a trvání opravy F2.

**Doporučení:** kdyby se ve vývoji pokračovalo, testovou sadu obnovit. Bez ní je
každá další změna ověřená jen tak důkladně, jak se zrovna podaří vymyslet ad hoc
kontroly.

---

*Ověřeno 7. 9. 2026 na macOS 25.6 (arm64) · bash 3.2.57 · grepai 0.36.1 ·
gitnexus 1.6.11 · qdrant přes OrbStack · ollama s nomic-embed-text-v2-moe.
Všechna čísla v tomto dokumentu pocházejí ze spuštěných testů, ne z odhadu.*
