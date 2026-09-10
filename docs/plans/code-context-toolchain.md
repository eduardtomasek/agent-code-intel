# Změna směru: vlastní nástrojový řetězec místo Graftu

Stav: **návrh k odsouhlasení.** Navazuje na
`docs/plans/graft-integration-analysis.md`, který skončil stanoviskem Graft
nepřidávat. Tento dokument popisuje, čím ho nahrazujeme, co je změřeno,
jak vypadá zamýšlený skill a jak se otestuje, než se zapracuje do produktu.

Datum měření: **2026-09-10.**

## 0. Rozhodnutí

**Přijato 2026-09-10.**

1. **Graft se nepřidává.** Každý jeho příkaz má levnější náhradu bez
   závislosti; poslední argument (mechanismus objevení) padl bránou C.
2. **`ctags` a `rg` jsou povinné v dokumentaci, ale v preflightu jen
   `warn`** — mají ověřené fallbacky (6.1). `ast-grep`, `fd`, `rga`,
   `tokei`, `scc` jsou silně doporučené. Instalaci řeší **nový samostatný
   režim `--install-deps`**; `--install` i `--apply` si zachovávají dnešní
   role.
3. **Zavádí se `SessionStart` hook — pro Claude i pro Codex.** Je to
   **nosný prvek celého řešení**, ne doplněk ke skillu. Oba agenti mají
   totožný výstupní kontrakt, takže sdílejí jeden skript; liší se jen
   registrace (`.claude/settings.json` vs `<repo>/.codex/hooks.json`).
   **Vše zůstává v repozitáři — do `~` nezapisujeme nic.** U Codexu musí
   `--apply` vypsat tři kroky, bez nichž je hook neaktivní (6.2).
4. **Skill `code-context`** je referenční příručka za hookem.
5. **Cílová verze 5.0.0.** Rozhodnuto 2026-09-10. Verze 5 byla zrušena
   jako „Graft edition"; obnovuje se s jiným obsahem — vlastní nástrojový
   řetězec, hook a `--install-deps`.

### Proč hook, a ne jen skill

Toto je nejdůležitější zjištění celé práce a je proti mému původnímu
očekávání. Měřeno na čerstvých headless relacích (`claude -p`), klasifikace
z jejich transcriptů:

| Běh | Hook | Skill zmíněn v zadání | Skill vyvolán | Odvozený přesný rozsah |
|---|---|---|---|---|
| výchozí stav (bez čehokoli) | ne | ne | ne | **1/9 = 11 %** |
| silná C, běh 1 | ne | ne | **ne** | **0/6 = 0 %** |
| silná C, běh 2 | ne | ano | ano | 4/4 = 100 % |
| **silná C, běh 3** | **ano** | **ne** | **ne** | **3/3 = 100 %** |

Čtou se z toho tři věci:

- **Obsah skillu funguje** (běh 2: 100 %).
- **Skill se sám nevyvolá** (běhy 1 a 3: ani jednou, přestože byl
  nainstalovaný a jeho `description` na úlohu sedí).
- **Pasivní instrukce nestačí.** V běhu 1 agent ignoroval i
  `agent-code-intel-routing` a `CLAUDE.md`, které GrepAI a GitNexus
  předepisují měsíce.

Rozdíl mezi 0 % a 100 % udělal hook — a **jen proto, že nenese odkaz na
skill, ale samotné pravidlo**: seznam nástrojů, konkrétní `ctags` příkaz,
zákaz hádání okna a zákaz `head`. Odkaz na skill je až na konci. Hook, který
by pouze ukazoval na skill, by dopadl jako běh 1.

**Rozpočet: 914 B `additionalContext` na session.** Původních 618 B nestačilo
— test na PHP ukázal, že hook musí nést i velikostní pojistku a rozcestník
`ctags` vs `ast-grep` podle jazyka (2.6). Je to strop, ne cíl; co se tam
nevejde, patří do skillu.

### Výsledky testování

| Brána | Kritérium | Výsledek |
|---|---|---|
| A — nákladová | ≤ 50 % ceny Graftu, přesnost 5/5 | **26 %, 5/5** ✅ |
| B — spustitelnost | 100 % příkazů skillu projde | **15/15** po opravě dvou chyb ✅ |
| C — behaviorální | ≥ 80 % odvozených rozsahů | **100 %** po zavedení hooku ✅ |
| D — jazyková a formátová | rozsahy v TS a PHP; rga na reálných datech | **splněna, odhalila dvě chyby ve skillu** ✅ |

Detaily jsou v sekcích 3 (náklad), 4.1 (spustitelnost) a 5 (brány).

## 1. Proč se směr změnil

Analýza Graftu skončila zjištěním, které nebylo v zadání: **problém nebyl
chybějící nástroj, ale chybějící disciplína.**

Autoaudit transcriptu (analýza Graftu, 9.7) ukázal, že tento agent v 6 z 9
čtení kódu hádal rozsah řádků místo aby ho odvodil, a jednou tím usekl
cílovou funkci v 70 % délky a závěr o jejím chování vzal z docstringu.
Graft se tomu jevil jako lék, protože prodává hotové rozsahy.

Měření ale ukázalo, že rozsahy umí levněji čtyři jiné cesty — a jedna z nich
byla po celou dobu nainstalovaná ve standardní knihovně. Graft tedy neprodává
schopnost, kterou nemáme; prodává **návyk, který nemáme zapsaný**.

Nový směr je proto: **nekupovat nástroj, ale zapsat návyk** — a doplnit ho
řetězcem nástrojů, které dělají totéž levněji a na víc jazyků.

**Skill ale není jen náhrada Graftu.** To by byl příliš úzký cíl. Jeho
úkolem je dát agentovi **schopnosti, které dnes nemá** — a část z nich
s Graftem nikdy nesouvisela: hledat uvnitř rotovaných logů a sqlite
databází (`rga`), vybírat soubory podle stáří a spustitelnosti (`fd`),
odhadnout, který soubor bude bolet (`scc`), a psát strukturální dotazy,
které jako regex nejdou napsat (`ast-grep`). Náhrada Graftu je jen jedna
z jeho sekcí.

## 2. Nástroje, které do stacku přibývají

Doinstalováno 2026-09-10, ověřené verze:

| Nástroj | Verze | Role | Verdikt |
|---|---|---|---|
| `ripgrep` | 15.2.0 | textové hledání, výčet referencí | **jádro** |
| `universal-ctags` | 6.2.1 | přesné rozsahy definic, API surface | **jádro** |
| `ast-grep` | 0.45.3 | strukturální hledání se znalostí syntaxe | **doplněk** |
| `fd` | 10.5.0 | výběr podle stáří, velikosti, spustitelnosti; `-X` | **vlastní role** |
| `rga` | 0.10.10 | hledání v `.gz` logách, sqlite, archivech, PDF | **vlastní role** |
| `tokei` | 15.0.0 | „co je tenhle repozitář" | doplněk |
| `scc` | 4.1.0 | „který soubor bolí" (složitost) | doplněk |

### 2.1 `universal-ctags` — nejdůležitější přírůstek

`--_xformat='%N L%n-%{end} %K'` dá jméno, začátek **i konec** definice.

- **Přesnost 10/10** na obou měřených sadách, rozsahy identické se
  stdlib `ast` i s Graftem.
- **Cílený dotaz stojí ~30 B.** Pro srovnání: `graft skeleton` vypíše
  841 B, aby řeklo totéž a k tomu 149 definic navíc.
- **164 jazyků** proti Graftovým osmi.

Omezení, které je nutné znát: u některých jazyků parser zná začátky, ale ne
konce. Na `test/run.sh` vydal konec jen u 2 ze 70 definic. Fallback —
odvodit konec ze začátku následující definice — dal správné rozsahy pro
všech 68 funkcí. Skill to pokrývá.

### 2.2 `ast-grep` — na to, co regex neumí

Hodnota je ve dvou věcech:

1. **Strukturální vzory**: `except $E: pass`, `open($$$A)` — dotazy, které
   jako regex buď nejdou napsat, nebo trefí komentáře a řetězce.
2. **Řeší slepé místo obou grafů.** Na `agent_skills.install_targets($$$A)`
   našel **19 volání**. `gitnexus_impact` i `graft callers` hlásí **nulu**,
   protože ani jeden neřeší cross-module `modul.funkce()`. V produkčním
   kódu je takových volání 83.

**Nepoužívat na vyhledání rozsahu symbolu** — jeho JSON nese celý zachycený
text a stálo to **113 %** ceny Graftu, tedy víc než nástroj, který má
nahradit. Na rozsahy je `ctags`.

### 2.3 `fd` — výběr souborů podle vlastností, ne obsahu

Na plané dotazy typu „všechny `.py`" dá `fd` **stejný výsledek jako
`rg --files`** (23 souborů). Jako náhrada je zbytečný. Jeho vlastní
schopnosti jsou tam, kde je kritériem **vlastnost souboru**, ne obsah:

| Dotaz | Příkaz | Ověřeno |
|---|---|---|
| co se nedávno změnilo | `fd -e py --changed-within 2d .` | ano |
| velké soubory | `fd -t f -S +100k .` | ano, našel `hero.jpg` |
| **spustitelné soubory** | `fd -t x .` | ano, 4 — `rg` to neumí vyjádřit |
| filtrovaná sada do **jednoho** `rg` | `fd -e py --changed-within 2d . -X rg -c 'def '` | ano, 22 řádků |

`-X` předá celou sadu jednomu procesu, `-x` spustí příkaz na každý soubor.
Pro agenta je skoro vždy správně `-X` — je to jeden průchod místo N.

### 2.4 `tokei` a `scc` — dvě různé otázky

- **`tokei`** (2,0 kB) odpovídá na „co je tenhle repozitář": jazyky,
  velikost, poměr kódu ke komentářům. Umí `--output json` pro strojové
  zpracování a bere víc cest naráz, což je použitelné v monorepu.
- **`scc --by-file --sort complexity`** (1,3 kB pro top 10) odpovídá na
  otázku, kterou neumí `tokei` ani Graft: **který soubor je složitý**.
  Vytáhl `commands.py` se složitostí 368, tedy 2,4× víc než druhý v pořadí.

**K tvé pochybnosti o `scc`:** přínos má, ale úzký. Jako počítadlo řádků je
`tokei` rychlejší a čitelnější. `scc` si drž kvůli sloupci Complexity
a `--by-file`. Jeho COCOMO odhady (`$364 239`, „9,37 měsíce, 3,45 lidí")
jsou pro agenta šum — o kódu, který se chystá měnit, neříkají nic. Skill je
výslovně označuje za ignorovatelné.

### 2.5 `rga` — oprava předchozího verdiktu

**V minulé verzi tohoto dokumentu jsem `rga` označil za „mimo". To byl
chybný závěr** — posuzoval jsem obecný nástroj podle obsahu jednoho
repozitáře. Stack má běžet i jinde.

Doměřeno, co `rga` reálně otevře:

**Bez jakékoli další instalace:**

| Formát | Ověřeno |
|---|---|
| `.gz .tgz .bz2 .xz .zst` | **ano** — shodu v `app.log.gz` našel, `rg` ji minul |
| `.db .sqlite .sqlite3` | **ano** — vrátil `cfg: k='endpoint', v='https://api.example/v2'` |
| `.zip .jar .tar` | podle adaptéru, rekurzivně dovnitř |

**Rotované logy a sqlite fixtures jsou přesně ty případy, kde `rg` nevrátí
nic a agent z toho vyvodí, že problém neexistuje.** To není pohodlí, to je
třída chyb.

**Vyžaduje externí binárku:**

| Formáty | Potřebuje |
|---|---|
| `.pdf` | `pdftotext` (poppler) |
| `.docx .odt .epub .ipynb .html` | `pandoc` |
| media metadata, titulky | `ffmpeg` |

Žádná z nich na tomto stroji není. `rga` v takovém případě **selže hlasitě**
na daném souboru, nepřeskočí ho tiše — což je správné chování, ale skill
na to musí upozornit, aby agent netvrdil „v dokumentaci nic není".

Drobnost: `.ipynb` je JSON, takže ho `rg` prohledá i bez `rga`. `rga` tam dá
čitelnější výstup, ale není podmínkou.

**Verdikt: `rga` do stacku patří**, jako volitelná závislost s jasně
popsanými hranicemi. `pandoc` a `pdftotext` doporučuji doinstalovat, pokud
budeš stack nasazovat na repozitáře s dodavatelskou dokumentací.

### 2.6 Na kterých jazycích to bylo skutečně ověřeno

**Toto je nejdůležitější omezení celé práce.** Chování nástrojů se mezi
jazyky liší natolik, že závěr naměřený na jednom jazyce se na druhý
nepřenáší. Dvakrát nás to v průběhu chytilo (D1 a PHP), pokaždé
u `ctags`.

| Jazyk | Projekt | Rozsah testu | `ctags` `%{end}` | Doporučený postup |
|---|---|---|---|---|
| **Python** | agent-code-intel (23 souborů) | úplný — všechny sekce skillu, brány A–D | **ano, 10/10 přesně** | `ctags` |
| **TypeScript** | combster-sis-api (856 souborů) | rozsahy definic, 170 definic ve 40 souborech | **ne, 0/170** | `ast-grep` kind pravidlo, 99,4 % |
| **PHP / Laravel** | wine-passport (123 souborů) | rozsahy, repo map, reference, `fd`, chování agenta | **ne, 0/145** | `ast-grep` kind pravidlo, 99,3 % |
| **Shell** | agent-code-intel (`test/run.sh`) | jen rozsahy | částečně, 2/70 | ruční fallback, 68/70 |
| ostatní ze 164, které `ctags` zná | — | **netestováno** | neznámé | zjistit podle postupu ve skillu §1 |

Co z toho plyne pro dokumentaci produktu: **uvádět, že přesnost je ověřená
na Pythonu, TypeScriptu a PHP**, a že pro ostatní jazyky skill obsahuje
postup, jak si to ověřit — ne slib, že to bude fungovat stejně.

Vzorec je zatím konzistentní: **`ctags` dává konce jen pro Python**;
u TypeScriptu i PHP je nula a správnou odpovědí je `ast-grep`. Není důvod
předpokládat, že jiný jazyk dopadne líp než ten horší z těch dvou.

## 3. Změřené výsledky

Baseline je Graft 0.16.0. Všechna čísla jsou bajty výstupu, který by
agentovi vstoupil do kontextu.

### 3.1 Získání jednoho symbolu (10 úkolů, sady T a N)

| Postup | bajtů | vs Graft | přesnost | jazyků |
|---|---|---|---|---|
| `graft skeleton` + rozsah | 63 478 | 100 % | 10/10 | 8 |
| `ast-grep` cílený | 71 677 | **113 %** | 10/10 | mnoho |
| `rg` v2 (odvození z výpisu) | 42 456 | 67 % | 10/10 | vzor na jazyk |
| stdlib `ast` cílený | 28 254 | 45 % | 10/10 | 1 |
| **`ctags` cílený** | **28 341** | **45 %** | **10/10** | **164** |

`ctags` a stdlib `ast` jsou nákladově nerozlišitelné; `ctags` vyhrává
pokrytím jazyků.

### 3.2 API surface souboru (amortizovaně)

| Postup | bajtů | vs Graft | obsahuje |
|---|---|---|---|
| `graft skeleton` | 47 382 | 100 % | jména, rozsahy, signatury |
| stdlib `ast` skeleton | 43 842 | 93 % | jména, rozsahy, signatury |
| **`ctags` skeleton** | **35 191** | **74 %** | jména, rozsahy, druh |

`ctags` je nejlevnější, protože signatury nevypisuje. Když jsou potřeba,
`%S` ve formátu je doplní za zhruba trojnásobek výstupu — pořád levněji
než Graft, ale ne defaultně.

### 3.3 Orientace v repozitáři

| Postup | bajtů | odpovídá na |
|---|---|---|
| `graft map` | 1 618 | co je centrální |
| **`rg` map** | **1 139 (70 %)** | co je centrální, shoda hotspotů **8/12** |
| `tokei` | 2 030 | co je tenhle repozitář |
| `scc --by-file` | 1 274 | který soubor bolí |

Na úzkou otázku, kterou `graft map` řeší, je `rg` map o 30 % levnější.
Spustit všechny tři stojí 4,4 kB, tedy 2,7× víc než Graft — ale odpovídají
na tři různé otázky, ne na jednu. Skill proto výslovně zakazuje pouštět je
všechny naráz.

### 3.4 Test skillu na neviděné sadě

Pátá sada úkolů (P1–P5), jiné symboly, jiné soubory, workflow přesně podle
skillu:

| # | Symbol | dotaz | rozsah | skill celkem | Graft |
|---|---|---|---|---|---|
| P1 | `run_status` | 31 B | 1 528 | 1 559 | 7 758 |
| P2 | `update_grepai_config` | 39 B | 1 935 | 1 974 | 4 730 |
| P3 | `qdrant_http_ok` | 31 B | 705 | 736 | 5 689 |
| P4 | `load` | 23 B | 1 936 | 1 959 | 4 574 |
| P5 | `_source_package` | 34 B | 162 | 196 | 2 044 |
| | **celkem** | | | **6 424** | **24 795** |

**Skill = 26 % ceny Graftu, přesnost 5/5.**

### 3.5 Jazykové pokrytí — obrácený argument

Poslední Graftova výhoda byla přenositelnost mezi jazyky. Test na
`test/run.sh` z tohoto repozitáře:

| | výsledek |
|---|---|
| `ctags` | 70 definic, po fallbacku 68 funkcí s rozsahem |
| `graft skeleton` | `no definitions indexed for this file` |

Graft shell mezi svými jazyky nemá. **Argument se otočil:** 164 jazyků
proti osmi, a Graft neuspěje ani na souboru v repozitáři, který indexoval.

## 4. Zamýšlený skill

Kanonický skill je v `agent_code_intel/assets/code-context/SKILL.md`.
Distribuuje se do agentních projektových adresářů jako spravovaný obsah.

Je psaný jako **schopnostní příručka**, ne jako seznam náhrad. Otevírá
tabulkou „co umí jen tenhle nástroj", protože to je rozhodnutí, které agent
dělá nejčastěji a nejhůř.

| Sekce | Co dává agentovi |
|---|---|
| Úvodní pravidlo | Nikdy nehádej rozsah, odvoď ho. Doloženo: hádání minulo cíl ve 3 z 5 případů, odvození stojí ~30 B |
| Co umí jen tenhle nástroj | Sedm řádků, sedm výlučných schopností — první věc, kterou agent přečte |
| Úloha → nástroj | Rozhodovací tabulka včetně hranic vůči GrepAI a GitNexusu |
| §1 Jeden symbol | `ctags` cílený + fallback pro jazyky bez `%{end}` |
| §2 API surface | `ctags` skeleton, `%S` jen na vyžádání |
| §3 Výčet referencí | `rg` / `ast-grep`, **výslovně ne graf**, s doloženou nulou od obou |
| §4 Strukturální hledání | `ast-grep`, vzory jako celé syntaktické jednotky |
| §5 Výběr souborů | `fd`: stáří, velikost, spustitelnost, `-X` |
| §6 Nečitelné formáty | `rga`: co jde bez instalace, co potřebuje pandoc/pdftotext |
| §7 Orientace | tři různé otázky, pouštět jen tu položenou |
| Driving `rg` well | scopování, počítání, `-e` union, `-o -r`, `-U`, a proč `-C` není na rozsahy |
| Tvrdá pravidla | stdin past, evidence gate, kontrola existence nástroje |

### 4.1 Ověření skillu příkaz po příkazu

Skill plný neotestovaných příkazů je závazek, ne pomoc. Proto jsem **spustil
každý příkaz, který v něm je**. Našly se dvě chyby, obě opravené:

1. **`ctags` neinterpretuje escape sekvence v `--_xformat`.** Doporučený
   fallback s `\t` vypisoval literální `JSON\t541\t543\theredoc`. Opraveno
   na oddělovač `|`, znovu ověřeno.
2. **`ast-grep` vzor `except $E: pass` nenajde nic**, protože `except` není
   v Pythonu samostatná syntaktická jednotka. Nahrazeno ověřenými vzory
   (`open($$$A)` → 32 zásahů, `subprocess.run($$$A)` → 30) a celým
   `try/except/pass` blokem → 17 zásahů. Skill k tomu přidal pravidlo:
   *když vzor vrátí nulu, podezřívej vzor, ne kód.*

Kdybych skill jen napsal a nespustil, obě chyby by se dostaly do produktu
a agent by z druhé z nich vyvodil, že repozitář nemá spolykané výjimky.

### 4.2 Past, kterou žádný ze zdrojů neuvádí

**`rg` bez cesty a s ne-tty stdinem prohledává stdin, ne adresář.** Volané
ze skriptu nebo hooku se `rg 'vzor' -tpy` zablokuje. Řešení: `rg 'vzor' -tpy .`

Opačná varianta platí taky: když do `rg` roura teče, cestu uvést nesmíš.
Obojí mě při stavbě kontenderů pokousalo a stálo dva zaseknuté procesy —
proto je to tvrdé pravidlo číslo jedna.

### 4.3 Licence a atribuce

Strategie scopování, počítání před čtením a batchování jsou převzaté
z `netresearch/file-search-skill` v1.8.0 (MIT AND CC-BY-SA-4.0). Atribuce je
ve frontmatteru. `skills.rest/ripgrep-dfpalhano` nepřinesl nic k převzetí.

## 5. Jak se skill otestuje

Čtyři brány. Teprve po jejich splnění se zapracuje do produktu.

### Brána A — nákladová (splněno)

Nová sada úkolů, workflow podle skillu, srovnání s Graftem.
**Kritérium: ≤ 50 % ceny Graftu při přesnosti 5/5.**
**Výsledek: 26 %, přesnost 5/5** (3.4).

### Brána B — spustitelnost (splněno)

Každý příkaz ve skillu musí projít.
**Kritérium: 100 % příkazů vrátí očekávaný typ výstupu.**
**Výsledek: 15/15 po opravě dvou chyb** (4.1).

Tuto bránu je nutné pustit znovu při každé změně skillu.

### Brána C — behaviorální (splněna po zavedení hooku)

Brána, na které celý směr stojí — přesně tady analýza Graftu selhala.

**Postup:** pět reálných otázek o tomto kódu, dosud v relaci neřešených,
zodpovězených striktně podle skillu; pak klasifikace každé čtecí operace.

| # | Otázka | Cíl | Postup |
|---|---|---|---|
| C1 | Jak `--remove` rozhoduje, co smí smazat? | `run_remove` L875-1047 | ctags → sed |
| C2 | Co dělá `_refresh_preflight` bez qdrantu? | L1613-1722 | ctags → sed → rg filtr |
| C3 | Jak `config.load` řeší ENV vs TOML? | L252-308 | ctags → sed |
| C4 | Co kontroluje `test_import_purity`? | L32-58 | ctags skeleton → sed |
| C5 | Co dělá `_source_package`? | L126-128 | ctags → sed |

**Výsledek:**

| Metrika | Hodnota | Kritérium |
|---|---|---|
| Cílený dotaz nebo odvozený rozsah | **5/5 = 100 %** | ≥ 80 % ✅ |
| Hádané okno | **0/5** | — |
| Useknutá cílová definice hádáním | **0/5** | žádné ✅ |

Referenční hodnota před zavedením byla **1 z 9 (11 %)**. Po zavedení
**100 %**. Kritérium splněno.

#### Nález: nový režim selhání, který skill nepokrýval

Ve **2 z 5** případů jsem správně odvozený rozsah **usekl přes `head`** —
C1 (80 ze 173 řádků) a C3 (30 z 57). Ověřením nepřečtených částí se
ukázalo, že závěry obstály, ale u C3 jen shodou okolností: chování větví
`toml` / `env` jsem popsal z **docstringu**, zatímco implementace ležela
v neviditelné části.

To je tentýž vzorec jako v analýze Graftu (9.7), jen o krok posunutý:
disciplína odvozování rozsahu se chytila, disciplína *dočtení* ne.

Skill dostal nové pravidlo: **rozsah, který jsi odvodil, neusekávej.** Když
je opravdu velký, filtruj uvnitř něj (`sed -n 'A,Bp' f | rg -n 'vzor'`), ne
`head` — filtr drží celý rozsah v záběru a řekne ti, co jsi přeskočil.

#### Omezení slabé verze

**Skill jsem psal já a mám ho v kontextu.** Slabá verze tedy prokazuje, že
pravidla jsou proveditelná a že je dodržím, když je mám před sebou —
neprokazuje, že si je vyzvedne agent, který skill najde studený.

### Brána C, silná verze — **NEPROŠLA na objevení, prošla na obsah**

Provedeno 2026-09-10 ve dvou čerstvých headless relacích (`claude -p`)
nad tímto repozitářem, se skillem nainstalovaným v
`.claude/skills/code-context/SKILL.md`. Klasifikace z jejich vlastních
transcriptů, ne z jejich odpovědí.

#### Běh 1 — skill nezmíněn v zadání

Zadání: tři věcné otázky o kódu, žádná zmínka o skillu ani o nástrojích.

**Skill nebyl vyvolán ani jednou.** Agent sáhl po harness nástrojích
`Grep` a `Read`, nikoli po `rg`, `ctags` nebo `fd`.

| Operace | Co udělal | Klasifikace |
|---|---|---|
| `Read config.py` | offset 245, limit 110 → 245–355 (cíl 252–308) | hádané okno |
| `Read commands.py` | offset 875, limit 175 → 875–1050 (cíl 875–1047) | kotva z grepu, hádaný konec |
| `Read test_import_purity.py` | celý (63 řádků) | celý soubor |
| `Grep -A 22` | kontextové okno | hádané okno |
| `Grep -A 25` | kontextové okno | hádané okno |
| `Grep -A 18` | kontextové okno | hádané okno |

**Odvozený rozsah: 0 ze 6 = 0 %.** Kritérium ≥ 80 % **nesplněno**.

Odpovědi přitom byly věcně správné a s přesnými citacemi — velkorysá okna
cíl pokryla. Selhal postup, ne výsledek. Tentokrát.

**Přitěžující nález:** agent nesáhl ani po GrepAI, ani po GitNexusu, ačkoli
`CLAUDE.md` i `agent-code-intel-routing` je předepisují. **Pasivní instrukce
nezměnily volbu nástrojů ani u skillu, který v projektu existuje měsíce.**

#### Běh 2 — zadání začíná „Použij skill code-context"

Stejný typ úkolu, jiné symboly.

| # | Operace | Klasifikace |
|---|---|---|
| 1 | `Skill code-context` | vyvolán |
| 2 | `rg -n -e A -e B -e C .` | union vzorů, jeden průchod, explicitní cesta |
| 3 | `ctags … \| rg -e '^run_status ' -e …` | cílený dotaz, union |
| 4 | `rg -n -l … .` + `fd -g '*seam*' .` | správné nástroje |
| 5 | `sed -n '1077,1132p'` + `sed -n '392,414p'` | **odvozené přesné rozsahy** |
| 6 | `ctags …` + `wc -l` | ověření velikosti před čtením |
| 7 | `sed -n '1,73p'` (soubor má 73 řádků) | celý soubor po ověření |
| 8 | `sed -n '1193,1229p'` | **odvozený přesný rozsah** |
| 9 | `rg -n … -C2` | kontext pro čtení shody, ne pro rozsah — skill to dovoluje |

**Odvozený rozsah nebo celý soubor po ověření velikosti: 4 ze 4 = 100 %.
Hádané okno: 0.** Agent sám v odpovědi napsal „rozsahy odvozené přes
`ctags`".

#### Závěr silné verze

| | Skill vyvolán | Disciplína |
|---|---|---|
| Běh 1 (nezmíněn) | **ne** | **0 %** |
| Běh 2 (zmíněn) | ano | **100 %** |
| Slabá verze (autor) | n/a | 100 % |

**Obsah skillu funguje. Jeho objevení ne.**

To je jiný problém, než jsme řešili — a je to problém, který Graft řeší
hooky. Skill, který se nevyvolá, nezmění chování, ať je napsaný jakkoli
dobře. Nejde tedy o „skill versus Graft", ale o to, že **skillu chybí
mechanismus objevení**.

Volby, od nejlevnější:

1. **Odkaz ve spravovaném bloku `CLAUDE.md` / `AGENTS.md`.** Mechanismus už
   máme (`_DOC_BLOCKS` v `commands.py`). **Ale běh 1 ukázal, že samotná
   zmínka nestačí** — blok tam dnes je a `agent-code-intel-routing`
   předepisuje, a agent to ignoroval. Nutné, ne dostatečné.
2. **Vlastní `SessionStart` hook**, který vloží jednu větu s rozhodovací
   tabulkou. Tohle je přesně Graftův mechanismus, jen bez Graftu a bez
   jeho ceny — pár řádků v `.claude/settings.json`, které si `--apply`
   spravuje sám.
3. **Přeformulovat `description` skillu** tak, aby triggeroval na „vysvětli
   / jak funguje / kde je". Nejlevnější, ale nejméně spolehlivé.

#### Náprava 1 + 2 a opakování brány — **SPLNĚNO**

Zavedeno 2026-09-10:

1. **Spravovaný blok `CLAUDE.md` / `AGENTS.md`** rozšířen o tři řádky
   odkazující na `code-context`, `ctags` a `rg`/`ast-grep`.
2. **Vlastní `SessionStart` hook** — `.claude/helpers/code-context-hint.py`
   registrovaný v `.claude/settings.json`. Emituje 774 B
   `additionalContext`.

Zásadní návrhové rozhodnutí u hooku: **nese to nejdůležitější pravidlo
přímo, ne odkaz na skill.** Vypisuje seznam dostupných nástrojů, konkrétní
`ctags` příkaz, zákaz hádání okna a zákaz `head`, a teprve na konci odkaz na
skill. Důvod je běh 1: skill, na který se jen ukáže, se nevyvolá.

**Opakovaný běh, nová sada symbolů, skill v zadání nezmíněn:**

| Cíl | Skutečný rozsah | Co agent přečetl | |
|---|---|---|---|
| `_apply_init` | L617-820 | `offset=617 limit=204` → 617-820 | **přesně** |
| `update_grepai_config` | L206-255 | `offset=206 limit=50` → 206-255 | **přesně** |
| `test_runtime_gate.py` | 67 řádků | celý, po dohledání přes `fd -H` | přiměřeně |

**Odvozený přesný rozsah: 3 ze 3 = 100 %. Hádané okno: 0.**
Kritérium ≥ 80 % **splněno**.

Agent použil `ctags -x --_xformat=…` na dva soubory naráz a `fd -H` —
nástroj, o jehož přítomnosti se dozvěděl z hooku.

**Skill přitom nebyl vyvolán ani v tomto běhu.** Práci odvedlo pravidlo
vložené hookem. To potvrzuje návrhové rozhodnutí výše a mění roli obou
částí:

- **hook je nosný prvek** — jediné, co prokazatelně mění chování;
- **skill je referenční příručka za ním** — pro případy, které se do
  774 B nevejdou (`rga`, `ast-grep` vzory, orientace v repu).

#### Shrnutí brány C

| Běh | Hook | Skill zmíněn | Skill vyvolán | Odvozený rozsah |
|---|---|---|---|---|
| silná, 1 | ne | ne | ne | **0/6 = 0 %** |
| silná, 2 | ne | ano | ano | 4/4 = 100 % |
| **silná, 3 (po 1+2)** | **ano** | **ne** | **ne** | **3/3 = 100 %** |
| slabá (autor) | n/a | n/a | n/a | 5/5 = 100 % |

Výchozí stav před vším: **1 z 9 = 11 %**.

**Brána C splněna.** Graft je tím zbytečný i v roli, kterou po běhu 1
vypadal, že si udrží — mechanismus objevení jsme postavili sami za 774 B
na session, bez závislosti a bez zápisu do `~/.claude`.

### Brána D — jazyková a formátová (splněna, s opravou skillu)

Provedeno 2026-09-10 na cizích datech, ne na tomto repozitáři.

#### D1 — rozsahy definic v jiném jazyce

Cíl: `combster-sis-api`, reálný projekt s 856 TypeScript soubory. Vzorek
40 souborů, 170 definic. Kontrola správnosti automatizovaná přes bilanci
závorek v odvozeném rozsahu.

| Postup | Správně | |
|---|---|---|
| `ctags` `%{end}` | **0 / 170** | parser pro TS konce **vůbec neemituje** |
| `ctags` + ruční fallback | 137 / 170 = **80,6 %** | **pod kritériem** |
| **`ast-grep` s `kind` pravidlem** | **170 / 171 = 99,4 %** | ✅ |

Jediná neshoda u `ast-grep` je chyba mého kontrolního testu — soubor
obsahuje pět šablonových literálů, které naivní počítání závorek rozbije.
Ověřeno ručně: `ast-grep` má rozsah správně. Reálně tedy 100 %.

**Proč ruční fallback selhal:** u poslední metody ve třídě spolkne
uzavírací závorku třídy. `findAll` má skutečný rozsah L67-82, fallback dal
L67-83. Systematická chyba u každého kontejneru, ne náhoda.

**Kritérium ≥ 90 % splněno — ale jiným nástrojem, než plán předpokládal.**

#### D2 — formáty, které `rg` nepřečte

Cíl: `~/Library/Logs/Adobe/GrowthSDK/Production` — 23 reálných rotovaných
logů `.log.gz` vedle nekomprimovaných. Měřeny jen počty souborů se shodou,
obsah logů se nečetl.

| Nástroj | Souborů se shodou na `error` |
|---|---|
| `rg` | 7 |
| **`rga`** | **29** |

`rga` dosáhl na **22 souborů navíc** — přesně ty komprimované.
**Kritérium splněno na reálných datech**, ne na syntetických fixtures.

#### D3 — kompletní test na PHP projektu

Cíl: `wine-passport`, reálný Laravel — 123 PHP souborů, 31 Blade šablon.

**Rozsahy definic** (vzorek 40 souborů, 145 definic):

| Postup | Správně |
|---|---|
| `ctags` `%{end}` | **0 / 145** |
| `ctags` + ruční fallback | 105 / 145 = **72,4 %** |
| **`ast-grep` s `kind` pravidlem** | **144 / 145 = 99,3 %** |

Jediná neshoda je znovu chyba mého kontrolního testu — `preg_match('/^#...')`
obsahuje `#`, který naivní stripování bere jako PHP komentář a sežere zbytek
řádku. Ověřeno ručně: `withValidator` má rozsah L39-52 správně. Reálně 145/145.

**Repo map** — druhá nalezená chyba ve skillu. Vzor `^\s*(?:def|class)`
z §7 našel na PHP **87 z 388 definic (22 %)**, protože PHP má `function`,
ne `def`. Opraveno na `ctags`, který je jazykově neutrální a najde všech 388.

**Ostatní sekce:** `fd` (`-t x` → 3, `--changed-within 30d` → 154),
`rg` i `ast-grep` na reference fungují beze změny. `rga` zde nemá co dělat —
projekt obsahuje jen PNG screenshoty, žádné archivy, logy ani sqlite. Potvrzuje
to, že hodnota `rga` je závislá na projektu, ne na jazyce.

**Chování agenta na PHP — dva běhy.**

*Běh 1, hook v původním znění (618 B, psaný podle Pythonu):* agent přečetl
**tři soubory celé**, `ctags` nepoužil. Soubory měly 30, 34 a 68 řádků při
mediánu projektu 38 — **číst je celé bylo správně**. Odhalilo to ale, že
kritérium „≥ 80 % odvozených rozsahů" je kalibrované na velké soubory a na
codebase z malých souborů měří špatnou věc.

*Oprava:* skill i hook dostaly **velikostní pojistku** — `wc -l` nejdřív,
pod ~100 řádků číst celé, nad tím odvozovat. Hook zároveň zjazykověl:
místo bezpodmínečného `ctags` říká, že při prázdném sloupci konce
(TypeScript, PHP) se má použít `ast-grep`. Rozpočet hooku tím vzrostl
z 618 B na **774 B** na session.

*Běh 2, opravený hook:*

| Krok | Co agent udělal |
|---|---|
| 1 | `fd … -x wc -l \| sort -rn` — **ověřil velikosti jako první** |
| 3 | `StoreProductRequest.php` (33 řádků) — přečetl celý |
| 4 | napsal si `ast-grep` `kind` pravidlo pro PHP |
| 5 | `ProductController.php` (141 řádků) `offset=53 limit=36` → **L53-88** |

Skutečný rozsah metody `show` je **L53-88**. **Přesně.**

**2/2 přiměřených operací = 100 %.** Skill nebyl vyvolán ani zde; opět
stačil hook.

#### Zpřesnění metriky brány C

Původní kritérium „≥ 80 % operací je odvozený rozsah" penalizovalo správné
chování na malých souborech. Nové znění:

> **≥ 80 % čtecích operací je buď odvozený rozsah, nebo přečtení celého
> souboru pod ~100 řádků po ověření velikosti.**

Přepočet podle nové metriky nemění žádný dřívější výsledek: v běhu 1 silné
brány C byla čtení nad soubory o 1828 a 587 řádcích, tedy hluboko nad prahem.

#### Dopad na skill — oprava

D1 vyvrátil tvrzení, které skill obsahoval: že `ctags` je univerzální
odpověď na rozsahy a `ast-grep` se na rozsahy používat nemá. To platilo
pro Python, kde bylo změřeno. **Pro TypeScript je to obráceně.**

Skill byl opraven na rozhodovací postup podle jazyka:

1. Zjisti jednou za jazyk, jestli `ctags` emituje `%{end}`.
2. **Emituje** → použij `ctags`, je přesný a nejlevnější.
3. **Neemituje a `ast-grep` jazyk umí** → použij `ast-grep` s `kind`
   pravidlem. Ne ruční fallback.
4. **Ani jedno** → ruční fallback, s vědomím ~1 řádku přesahu u kontejnerů.

Zákaz „nepoužívej `ast-grep` na rozsahy" byl zúžen na jazyky, kde `ctags`
konce dává.

Tohle je nejcennější výstup brány D: **plán stál na měření z jednoho
jazyka a zobecnil ho neprávem.** Bez cizího repozitáře by chyba prošla
do produktu.

## 6. Co se zapracuje do produktu

Rozhodnuto 2026-09-10.

### 6.1 Závislosti a jejich přísnost

Rozhodnuto 2026-09-10 po rozboru toho, co `--install` a `--apply` dnes
skutečně dělají.

**Dnešní dělba práce je ostrá a zachovává se:**

| Režim | Co dělá dnes |
|---|---|
| `--install` | instaluje **jen vlastní produkt** — lib, launcher, `code-intel-dash`, šablonu konfigurace, pravidlo v `~/.claude/settings.json` |
| `--apply` | cizí závislosti **jen kontroluje** (`grepai`, `gitnexus`, `curl`, `git`, `claude`/`codex`, node, qdrant, ollama); chybějící = `_Need` a konec |

Původní návrh („`--install` nabídne `brew`") tuto dělbu porušoval. Navíc by
nikdy nebyl úplný: **`grepai` ani `gitnexus` v Homebrew nejsou** (Go binárka
a npm balíček), zatímco všech sedm nových nástrojů ano.

#### Rozhodnutí: nový režim `--install-deps`

| Nástroj | Přísnost | Chybí → |
|---|---|---|
| `rg`, `ctags` | doporučené, s fallbackem | **`warn`**, ne blokace |
| `ast-grep`, `fd`, `rga`, `tokei`, `scc` | silně doporučené | `warn` |
| `grepai`, `gitnexus`, `curl`, `git` | povinné (beze změny) | `_Need`, blokace |

- **`--install-deps`** — nový samostatný režim. Zkontroluje všech devět
  nástrojů, na macOS nabídne `brew install` pro těch sedm, které v brew jsou,
  a pro `grepai` / `gitnexus` vypíše jejich vlastní instalační příkaz.
  Nikdy neinstaluje bez potvrzení; bez TTY jen vypíše příkazy.
  Mimo macOS se `brew` nenabízí, vypíše se seznam balíčků.
- **`--install` zůstává beze změny.** Na konci přidá jednu větu:
  „chybí X, Y — spusť `agent-code-intel --install-deps`".
- **`--apply` zůstává kontrolní.** Nikdy nic neinstaluje.
- Mapování názvů patří do kódu: `rga` → `ripgrep-all`,
  `ctags` → `universal-ctags`, `rg` → `ripgrep`.

#### Proč `rg` a `ctags` jen `warn`

Rozlišujeme dvě různé přísnosti, které jsme dřív slévali do jedné:
**„povinné v dokumentaci"** (skill a README je předpokládají) versus
**„blokující v preflightu"** (bez nich tool odmítne pracovat). `ctags` a `rg`
jsou to první, ne to druhé.

Původně to mělo i druhý důvod: v minor verzi by blokace shodila existující
projekty na strojích bez `ctags`. **Rozhodnutím vydat to jako 5.0.0 ten důvod
odpadá** — major verze breaking change unese.

Zůstává ale ten první, a ten je silnější: **blokovat kvůli nástroji, jehož
absenci umíme přesně nahradit, je zbytečné.** Python je krytý stdlib vždy,
nepythonové jazyky `ast-grepem`. Blokace by nic nezachránila, jen by odmítla
práci, kterou tool zvládne. `rg` se navíc dnes nekontroluje vůbec, takže by
šlo o zcela nový důvod k selhání.

Ověřené fallbacky (2026-09-10):

| Chybí | Python | TypeScript / PHP |
|---|---|---|
| `ctags` | stdlib `ast` — **přesné**, ověřeno 10/10 | `ast-grep` — **přesné**, 99,3–99,4 % |
| `ctags` **i** `ast-grep` | stdlib `ast` — **přesné** | **jen `grep`: začátky ano, konce odvozené — 72–81 %** |
| `rg` | `grep` + roura — funguje, ztrácí `-t` typy a znalost `.gitignore` | totéž |

**Jediná skutečně degradovaná kombinace je „ani `ctags`, ani `ast-grep`
na nepythonovém kódu".** Preflight proto nemá hlásit `warn` za každý
chybějící nástroj zvlášť, ale navíc **jeden zřetelný `warn`, když chybí
oba** — to je stav, kdy rozsahy definic přestanou být spolehlivé.

Povýšení `ctags` na blokující zůstává možností do budoucna, ale ne kvůli
verzování — jen tehdy, kdyby se ukázalo, že fallbacky v praxi nestačí.

#### Externí binárky pro `rga`

`pandoc`, `pdftotext`, `ffmpeg` se **nenabízejí ani nekontrolují** — jsou to
závislosti adaptérů pro formáty, které většina repozitářů nemá. Zmínka patří
do dokumentace k `rga`, kde je i to, že `rga` na takovém souboru selže
hlasitě, ne tiše.

### 6.2 `SessionStart` hook — nosný prvek, ne doplněk

Brána C ukázala, že **skill sám chování nezmění, protože se nevyvolá**.
Mění ho hook. `--apply` proto musí spravovat i ten:

| Soubor | Obsah |
|---|---|
| `.claude/helpers/code-context-hint.py` | emituje `additionalContext` (914 B) |
| `.claude/settings.json` | registrace `SessionStart` hooku |

Pravidla, která si po Graftu vynucujeme a musíme dodržet sami:

- **Jen repo-local.** Žádný zápis do `~/.claude` ani `~/.claude.json`.
  Přesně to, co jsme Graftu vyčítali (R1).
- **Merge, ne přepis.** `.claude/settings.json` může mít cizí obsah;
  `--apply` mergne svůj blok a zbytek nechá být, `--remove` odstraní jen
  vlastní.
- **Žádný `statusLine`.** Kolidoval by s `code-intel-dash`.
- **Rozpočet.** 914 B na session je strop, ne cíl. Každé rozšíření hooku
  se platí každou session — obsah, který se tam nevejde, patří do skillu.
- **`--no-hook`** pro projekty, kde si uživatel hooky spravuje sám.

#### Codex hook — součást verze 5

Rozhodnuto 2026-09-10. Zdroj: `developers.openai.com/codex/hooks.md`
(totožné s `learn.chatgpt.com/docs/hooks`), ověřeno proti `codex-cli 0.139.0`.

**Graftův README se mýlil.** Tvrdil, že Codex hooky jsou jen uživatelské
a platí pro každý repozitář. Dokumentace uvádí čtyři místa, mezi nimi
**`<repo>/.codex/hooks.json`**. Projektové hooky Codex podporuje, což je pro
nás podmínka — do `~` nezapisujeme nic.

**Výstupní kontrakt je totožný s Claude Code:**

```json
{"hookSpecificOutput": {"hookEventName": "SessionStart",
                        "additionalContext": "…"}}
```

`code-context-hint.py` tedy poslouží **oběma agentům beze změny**. Liší se jen
registrace.

| | Claude Code | Codex |
|---|---|---|
| Registrace | `.claude/settings.json` | `<repo>/.codex/hooks.json` |
| `timeout` | **milisekundy** | **sekundy** (default 600) |
| Cesta ke skriptu | `${CLAUDE_PROJECT_DIR}` | absolutní, nebo z git rootu |
| Navíc | — | `statusMessage`, `additionalContextLimit`, `async` |

##### Upřesnění principu „všechno per projekt"

Platí pro to, **co zapisujeme my**: hook i skript jsou v repozitáři, mimo něj
nesaháme.

**Neplatí pro stav důvěry.** Codex si vede globálně v `~/.codex/config.toml`:

```toml
[hooks.state."<absolutní cesta k hooks.json>:<událost>:0:0"]
enabled = true
trusted_hash = "sha256:…"
```

Tyto záznamy **nepíšeme my** — vytváří je Codex, když uživatel hook schválí.
Je ale poctivé to vědět: projektový hook má globální stopu, na kterou nemáme
vliv a kterou `--remove` neuklidí.

##### Tři brány, které musí být splněné

Vyplynuly z testování a **všechny tři musí být v dokumentaci pro Codex**:

1. **`[features] hooks` nesmí být `false`.** Na tomto stroji je
   `hooks = false` — hooky jsou globálně vypnuté a projektový hook tiše
   nedělá nic. Toto je nejzrádnější z bran, protože nikde nevyskočí chyba.
2. **Projektová vrstva `.codex/` musí být důvěryhodná**, jinak se projektové
   hooky vůbec nenačtou.
3. **Hook musí být schválen** přes `/hooks` v CLI. Schvaluje se **definice
   v `hooks.json`**, ne obsah skriptu — stačí to tedy jednou, pokud
   `--apply` definici nemění.

##### Co musí `--apply` vypsat

Při zápisu **nebo změně** Codex hooku (ne jen při prvním vytvoření — důvěra
je vázaná na hash, takže každá změna vyžaduje nové schválení):

```
codex: zapsán .codex/hooks.json

  Hook je neaktivní, dokud neuděláš tohle:
  1) ověř, že v ~/.codex/config.toml NENÍ [features] hooks = false
  2) otevři projekt v Codexu a potvrď důvěru projektu
  3) spusť /hooks a hook schval

  Stačí jednou. Další upgrady agent-code-intel schválení neruší.
```

Hlášení se vypisuje **jen když `--apply` `hooks.json` skutečně vytvořil nebo
změnil** — ne při každém běhu. Když je soubor bajtově shodný, mlčí.

`--status` má hlásit existenci souboru; **schválení ověřit neumí** — stav
důvěry je v Codexu, ne u nás. Hlásit ho jako „zapsáno, schválení neověřeno".

##### Na co přesně se váže důvěra — ověřeno, a je to lepší, než jsem čekal

Původně jsem zapsal, že se důvěra váže na text hooku, a doporučil ho zmrazit
na neměnné jádro. **Měření to vyvrátilo.**

Dva testy:

| Změna | Hook po ní běží? |
|---|---|
| **obsah skriptu** (`code-context-hint.py` — doplněn `TMPDIR=.`) | **ano**, nový text dorazil do kontextu bez nového schválení |
| **`hooks.json`** (jen `timeout` 5 → 6) | **ne**, hook přestal běžet |

**Důvěra se váže na definici hooku v `hooks.json`, ne na obsah skriptu.**

Důsledek je pro nás velmi příznivý:

- **Text hooku smíme mezi verzemi měnit volně.** Upgrade
  `agent-code-intel`, který mění jen znění hlášky, Codex uživatele
  neodstřihne.
- **Stabilní musí být `hooks.json`** — stejný příkaz, stejná cesta, stejný
  timeout, stejná událost. Pak stačí **jediné schválení** za život projektu.
- Cesta ke skriptu je řešená přes `$(git rev-parse --show-toplevel)`, takže
  definice je **nezávislá na stroji i na umístění repozitáře** — přesun ani
  naklonování schválení neruší (ověřeno níže).

**Doporučení „zkrátit hook na neměnné jádro" se tím ruší.** Hook si smí
ponechat naměřená čísla i příklady; jediné, co `--apply` musí držet bajtově
stabilní, je `hooks.json`.

Nedoověřeno: po vrácení `timeout` zpět na 5 by se měla důvěra obnovit sama
(hash odpovídá uloženému `trusted_hash`), ale ověřovací běh zamrzl a
nepotvrdil jsem to. Pokud by hook po experimentu neběžel, stačí `/hooks`.

##### Ověřeno spuštěním 2026-09-10 — **funguje**

Po zapnutí `[features] hooks = true` a schválení hooku přes `/hooks` je celý
řetěz ověřený koncem ke konci.

`/hooks` v tomto repozitáři vypsal:

```
Event     SessionStart
Source    Project config - ~/Work/Personal/agent-code-intel/.codex/hooks.json
Command   /usr/bin/env python3 …/.claude/helpers/code-context-hint.py
Timeout   5s
Trust     Trusted
```

**`Source: Project config` je doklad, že `codex-cli 0.139.0` projektové hooky
umí.** Hypotéza, že je neumí a je potřeba `codex update`, je tím vyvrácená.

Kontrola, že obsah dorazí do kontextu (dotaz na frázi, která je **jen**
v hooku):

```
ANO. „Code context tooling here: rg, ctags, ast-grep, fd, rga, tokei, scc."
```

**Skutečným blokátorem byla po celou dobu důvěra hooku**, ne formát, ne cesta,
ne verze. `codex exec` hooky spouští — jakmile jsou schválené; ve výstupu se
objeví řádek `hook: … Completed`.

##### Behaviorální test na Codexu

Dotaz na dvě funkce, bez zmínky o skillu. Codex sám napsal:

> „Nejdřív dohledám přesné definice a pak si přečtu jen jejich rozsahy podle
> `ctags`, aby odpověď stála na zdroji, ne na odhadu."

Pak spustil `wc -l` na oba soubory — **velikostní pojistka z hooku** — a když
`ctags` selhal, přešel na `ast-grep`, tedy přesně na fallback, který hook
předepisuje. **Hook mění chování i na Codexu.**

##### Nové zjištění: `ctags` selhává pod sandboxem Codexu

`ctags` si otevírá dočasný soubor pod systémovým `$TMPDIR`, což sandbox
odmítne:

```
ctags: cannot open temporary file: /var/folders/…/T//tags.JLhAzJ : Operation not permitted
```

**A pipeline přesto vrací exit 0.** Selhání je tedy tiché a agent dostane
prázdný výsledek, který vypadá jako „takový symbol neexistuje". To je horší
než hlasitá chyba.

| Varianta | Výsledek pod Codexem |
|---|---|
| `ctags …` | **selže tiše** |
| `ctags --sort=no …` | selže také — řazení není příčina |
| **`TMPDIR=. ctags …`** | **funguje** |
| `ast-grep` | funguje vždy |

`TMPDIR=.` byl doplněn **do hooku i do skillu** (hook tím vyrostl na 914 B).
Ověřeno, že v repozitáři nenechává žádný zbytkový soubor. V režimu, kde je
i workspace read-only, `ctags` nepoužívat vůbec a jít rovnou na `ast-grep`.

##### Přenositelnost `.codex/hooks.json` — ověřeno, je plná

Ověřeno 2026-09-10 po schválení nové definice přes `/hooks`:

```json
"command": "/usr/bin/env python3 \"$(git rev-parse --show-toplevel)/.claude/helpers/code-context-hint.py\""
```

| Test | Výsledek |
|---|---|
| spuštění z kořene repozitáře | hook vystřelil |
| spuštění z podadresáře `test/` | **hook vystřelil** |

**Důsledky:**

- `.codex/hooks.json` **neobsahuje žádnou absolutní cestu** — je nezávislý
  na stroji i na umístění repozitáře.
- **Patří tedy do gitu**, ne do `.gitignore`. Kolega po naklonování jen
  jednou spustí `/hooks`.
- Definice zůstává napříč stroji bajtově stejná, takže se schválení
  neruší při přesunu ani při upgradu.
- `--apply` ho generuje jako **konstantu**, ne per projekt.

**Oprava dřívějšího tvrzení.** Dříve jsem sem zapsal, že `$(...)` v `command`
způsobuje zamrznutí `codex exec` a je nutné použít absolutní cestu. **Není to
pravda.** Zámrzy `codex exec` se ten den objevovaly opakovaně i bez hooků
a s absolutními cestami; se subshellem nesouvisely.

##### Praktické poznámky z testování

- **Test na obsah hooku musí používat řetězec, který se nevyskytuje jinde.**
  První pokus vypadal úspěšně, ale model citoval spravovaný blok
  z `AGENTS.md`, který Codex načítá sám. Kontrola na hook-only frázi to
  odhalila.
- Uživatelská `~/.codex/config.toml` byla po každém pokusu obnovena ze zálohy
  a ověřena jako bajtově shodná; dočasný `~/.codex/hooks.json` byl smazán.

### 6.3 Zbytek update

1. **Skill `code-context`** do `agent_code_intel/assets/`, distribuovaný
   stejným byte-identickým mechanismem jako `agent-code-intel-routing`
   (`agent_skills.py`), pro Claude i Codex.
2. **`agent-code-intel-routing` rozšířit** o odkaz na `code-context` a o dvě
   pravidla platná bez ohledu na zbytek:
   - výčet referencí u cross-module volání patří `rg`/`ast-grep`, ne grafu;
   - rozsah definice se odvozuje, nehádá — a neusekává.
3. **Spravovaný blok `CLAUDE.md` / `AGENTS.md`** (`_DOC_BLOCKS`) rozšířit
   o tři řádky odkazující na `code-context`.
4. **Codex hook**: zápis `<repo>/.codex/hooks.json`, sdílený skript
   s Claude, hlášení tří kroků k aktivaci při vytvoření nebo změně souboru
   (6.2). Definice je **konstantní a přenositelná** (`$(git rev-parse
   --show-toplevel)`), takže se commituje a schválení přežije přesun
   i upgrade. `--status` hlásí existenci, ne schválení.
5. **Nový režim `--install-deps`** v `cli.py` (`_MODE_FLAGS`) a
   `commands.py`, s mapováním názvů balíčků a detekcí platformy podle
   `platform.system()`.
6. **README** rozšířit o sekci závislostí ve třech úrovních, `--install-deps`,
   `--no-hook`, o výslovné uvedení, že přesnost rozsahů je ověřená na
   Pythonu, TypeScriptu a PHP (2.6), a o **samostatnou sekci pro Codex**
   s těmi třemi branami — bez nich hook tiše nefunguje.
7. **Verze 5.0.0.** Rozsah je na major: nový skill, nový spravovaný hook
   zapisující do `.claude/settings.json` (soubor, na který jsme dosud
   nesahali), nový režim `--install-deps`, rozšířený spravovaný blok
   v `CLAUDE.md` / `AGENTS.md` a nová dimenze driftu ve `--status`.
   `ctags` a `rg` přesto zůstávají `warn`, ne blokace — mají ověřené
   fallbacky (6.1), takže z uživatelského pohledu nic nepřestává fungovat.

## 7. Otevřené otázky

1. ~~Zkrátit text hooku na neměnné jádro~~ — **odpadá.** Ověřeno, že se
   důvěra váže na `hooks.json`, ne na text (6.2). Codex hook je hotový.
3. Samostatný skill `code-context`, nebo vše do `agent-code-intel-routing`?
   Návrh je samostatný — routing je stabilní a otestovaný 260 unit testy
   a 53 scénáři.
4. **Jazyky mimo Python, TypeScript a PHP** (2.6) — dokumentace je má
   označit za neověřené. Chceš před vydáním doměřit ještě nějaký konkrétní
   jazyk, který reálně používáš?
5. Kdy odinstalovat Graft? Po čtyřech splněných branách pro něj nevidím
   použití.

## Zdroje

- Měření 2026-09-10 nad tímto repozitářem: sady úkolů T, N a P;
  kontendery `ctags`, stdlib `ast`, `rg` v2, `ast-grep`, `rg` map;
  baseline Graft 0.16.0 v izolovaném klonu
- Cizí projekty pro brány D1 a D3: `combster-sis-api` (856 TS souborů),
  `wine-passport` (123 PHP souborů, Laravel) — vše čteno read-only;
  `~/Library/Logs/Adobe/GrowthSDK` pro D2 (měřeny jen počty shod)
- `netresearch/file-search-skill` v1.8.0 (MIT AND CC-BY-SA-4.0)
- `burntsushi/ripgrep`; Universal Ctags 6.2.1; ast-grep 0.45.3;
  fd 10.5.0; tokei 15.0.0; scc 4.1.0; ripgrep-all 0.10.10
- `docs/plans/graft-integration-analysis.md` — předchozí analýza a stanovisko
- `agent_code_intel/assets/code-context/SKILL.md` — kanonický skill
