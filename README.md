# Code intelligence pro AI agenty

Tato dokumentace popisuje instalaci celého stacku na Macu. Předpokládá pouze
základní práci s aplikacemi; všechny potřebné kroky jsou vysvětlené.

Po dokončení se nové projekty nastavují takto:

```
mkdir ~/projects/muj-projekt
cd ~/projects/muj-projekt
agent-code-intel --agent claude --apply
```

AI kódovací agent pak umí hledat v kódu podle významu, ne pouze podle
klíčových slov, a vyhodnotit dopad změn.

> `--agent claude` tam nechybí náhodou. Bez něj skript vyžaduje i Codex a
> odmítne se spustit, pokud Codex není nainstalovaný. Při použití obou agentů
> lze přepínač vynechat.

---

## Rychlý start

Toto je nejkratší postup pro nový Mac. Příkazy spouštějte **po jednom** a na
další přejděte až po návratu řádku s `%`. Pokud Homebrew po instalaci vypíše
další příkazy pro nastavení PATH, nejdříve spusťte právě tyto pokyny.

Nejdříve ověřte Git:

```
git --version
```

Pokud příkaz selže, macOS nabídne instalaci vývojářských nástrojů. Dokončete
ji a Git zkontrolujte znovu:

```
xcode-select --install
git --version
```

Pak nainstaluj Homebrew, Python, kontejnery, lokální embeddingy, Node.js a
vyhledávací nástroje:

```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python
python3 --version
brew install --cask orbstack
open -a OrbStack
brew install ollama
brew services start ollama
brew install node
npm i -g gitnexus
brew install yoanbernabeu/tap/grepai
brew install ripgrep
```

`ripgrep` poskytuje příkaz `rg`. Je volitelný, ale routing skill ho použije pro
přesné hledání a závěrečné ověření; bez něj zůstávají GrepAI a GitNexus
funkční. Po prvním otevření OrbStacku vyčkej, až dokončí nastavení, a ověř ho:

```
docker info
```

Nakonec stáhni tento projekt, nainstaluj jeho lokální kopii a zapni inteligenci
v prvním projektu:

```
git clone https://github.com/eduardtomasek/agent-code-intel.git ~/src/agent-code-intel
cd ~/src/agent-code-intel
python3 ./agent-code-intel --install
mkdir -p ~/projects/muj-projekt
cd ~/projects/muj-projekt
agent-code-intel --agent both --apply
```

Místo posledního příkazu použij `--agent claude`, pokud má projekt obsluhovat
jen Claude, nebo `--agent codex`, pokud jen Codex. `both` nastaví oba.

## Aktualizace na 4.1.0

Aktualizace vždy začíná checkoutem, ze kterého jsi nástroj instaloval. Stáhni
nový zdroj, znovu nainstaluj **lokální soubor** a pak v každém projektu obnov
spravované artefakty:

```
cd ~/src/agent-code-intel
git pull --ff-only
python3 ./agent-code-intel --install
cd /cesta/k/projektu
agent-code-intel --agent both --apply
```

Používáš-li jen jeden agent, poslední řádek nahraď jednou z variant:

```
agent-code-intel --agent claude --apply
agent-code-intel --agent codex --apply
```

`--install` bezpečně aktualizuje vlastní instalovanou kopii a zachová tvoji
konfiguraci. `--apply` je idempotentní: identický routing skill nechá beze
změny a jinak aktualizuje pouze artefakty vybraného agenta.

---

## Obsah

0. [Rychlý start](#rychlý-start)
1. [Aktualizace na 4.1.0](#aktualizace-na-410)
2. [Co to vlastně dělá](#1-co-to-vlastně-dělá)
3. [Co budeš potřebovat](#2-co-budeš-potřebovat)
4. [Terminál — základ](#3-terminál--základ)
5. [Homebrew](#4-homebrew)
6. [OrbStack — kontejnery](#5-orbstack--kontejnery)
7. [Ollama — embedding model](#6-ollama--embedding-model)
8. [Node.js](#7-nodejs)
9. [GrepAI](#8-grepai)
10. [GitNexus](#9-gitnexus)
11. [agent-code-intel](#10-agent-code-intel)
12. [První projekt](#11-první-projekt)
13. [Ověření, že to funguje](#12-ověření-že-to-funguje)
14. [Každodenní používání](#13-každodenní-používání)
15. [Dashboard — přehled o všem najednou](#14-dashboard--přehled-o-všem-najednou)
16. [Když se něco pokazí](#15-když-se-něco-pokazí)
17. [Odinstalace](#16-odinstalace)
18. [Slovníček](#17-slovníček)

---

## 1. Co to vlastně dělá

Když AI agent pracuje s tvým kódem, musí se v něm nejdřív zorientovat. Bez
pomoci to dělá tak, že hledá textové řetězce — jako když v editoru zmáčkneš
Cmd+F. To funguje, dokud víš, co přesně hledat. Jakmile chceš „najdi místo, kde
se ověřuje heslo", a ta funkce se jmenuje `validateCreds`, textové hledání
selže.

Tenhle stack přidává dvě věci, které to řeší jinak.

**GrepAI** čte tvůj kód a každý jeho kousek převede na sadu čísel, která
zachycuje význam — takzvaný vektor. Když se pak zeptáš větou, převede se stejným
způsobem i tvoje otázka a najdou se kousky kódu, jejichž čísla jsou nejblíž.
Proto najde `validateCreds`, i když jsi slovo „validate" nenapsal. Tomuhle se
říká sémantické vyhledávání.

**GitNexus** staví mapu vztahů: co odkud volá, co na čem závisí. Odpovídá na
otázky typu „když změním tuhle funkci, co všechno se může rozbít". To je něco,
co ze samotného textu nevyčteš.

Obojí běží **výhradně u tebe na počítači**. Žádný kód nikam neodchází.

Jeden příkaz, `agent-code-intel`, tohle všechno pro nový projekt nastaví najednou
a zároveň napíše tvému AI agentovi instrukce, kdy má co použít.

### Z čeho se to skládá

| Součást              | Co dělá                             | Proč je potřeba                         |
| -------------------- | ----------------------------------- | --------------------------------------- |
| **Ollama**           | Převádí text na vektory             | Bez ní není z čeho hledat               |
| **qdrant**           | Databáze vektorů, běží v kontejneru | Ukládá a prohledává, co ollama vyrobila |
| **OrbStack**         | Spouští kontejnery                  | Hostitel pro qdrant                     |
| **GrepAI**           | Sémantické vyhledávání              | Řídí indexování a hledání               |
| **GitNexus**         | Mapa vztahů v kódu                  | Odpovídá na „co se rozbije"             |
| **Node.js**          | Běhové prostředí                    | GitNexus je v něm napsaný               |
| **ripgrep (`rg`)**   | Přesné hledání a ověření            | Volitelný nástroj pro routing skill     |
| **Homebrew**         | Správce balíčků                     | Instaluje většinu z výše uvedeného      |
| **agent-code-intel** | Propojí to všechno                  | Aby to byl jeden příkaz, ne patnáct     |

Připrav si zhruba **20 minut** a **5 GB místa na disku**. Většina času je čekání
na stahování.

---

## 2. Co budeš potřebovat

- Mac s macOS — návod je psaný pro Apple Silicon i Intel
- Pro verzi 4.1.0 Python 3.11 nebo novější; po instalaci ověřte, že
  `python3 --version` vypíše alespoň 3.11. Python 3.9 a starší skončí
  srozumitelnou chybou bez tracebacku
- Připojení k internetu
- Heslo ke svému účtu na Macu, jednou při instalaci Homebrew
- Claude Code, VS Code nebo jiný agent, který umí MCP

Nemusíš umět programovat. Nemusíš rozumět tomu, co jednotlivé příkazy dělají —
u každého je napsané, co se stane a jak poznáš, že to vyšlo.

---

## 3. Terminál — základ

Terminál je aplikace, kde se počítači píšou příkazy místo klikání. Otevřeš ho
takto: zmáčkni **Cmd + mezerník**, napiš `Terminál` a dej Enter.

Objeví se okno s řádkem, který končí znakem `%`. Za něj se píše.

Tři věci, které ti ušetří trápení:

**Příkazy kopíruj po jednom.** Zkopíruj řádek, vlož do terminálu, dej Enter,
počkej, až se objeví nový řádek s `%`. Teprve pak další. Když vložíš víc řádků
najednou a jeden z nich je rozdělený, terminál zahlásí chybu.

**Když se nic neděje, čeká se.** Stahování a instalace trvají. Dokud se
neobjeví nový řádek s `%`, příkaz běží. Nepřerušuj ho.

**Terminál nezavírej** dokud nebudeš hotový, ať se ti neztratí kontext.

Vyzkoušej si to. Napiš:

```
echo ahoj
```

Musí to vypsat `ahoj`. Když ano, umíš vše potřebné.

---

## 4. Homebrew

Homebrew je správce balíčků — jednou příkazem nainstaluje program, který bys
jinak musel hledat a stahovat ručně. Většina dalších kroků ho používá.

Nejdřív zjisti, jestli ho už nemáš:

```
brew --version
```

Když to vypíše číslo verze, přeskoč na krok 5. Když to řekne `command not
found`, nainstaluj ho:

```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Instalátor se zeptá na heslo k tvému účtu. Při psaní hesla se **nic
nezobrazuje** — ani hvězdičky. To je normální, piš a dej Enter.

Na konci může Homebrew napsat něco jako „Run these commands in your terminal to
add Homebrew to your PATH" a pod tím dva až tři příkazy. **Ty příkazy spusť** —
jinak `brew` nebude fungovat. Zkopíruj je přesně tak, jak je vypsal.

Kontrola:

```
brew --version
```

Musí vypsat verzi. Pokud pořád `command not found`, zavři terminál, otevři nový
a zkus znovu.

---

## 5. OrbStack — kontejnery

Kontejner je izolované prostředí, ve kterém běží jeden program. Databáze
qdrant, kterou stack potřebuje, běží právě takhle — nemusíš ji instalovat do
systému, jen ji spustíš jako kontejner.

OrbStack je aplikace, která kontejnery na Macu spouští. Je rychlejší a šetrnější
k baterii než Docker Desktop, ale pokud už Docker Desktop máš, tenhle krok
přeskoč.

```
brew install --cask orbstack
```

Stahuje se zhruba 100 MB. Po instalaci OrbStack **spusť** — Cmd + mezerník,
napiš `OrbStack`, Enter. Při prvním spuštění se tě zeptá na pár věcí, výchozí
volby stačí.

V nastavení OrbStacku si zapni spouštění po přihlášení. Ušetří ti to
každodenní „proč to nefunguje" — bez běžícího OrbStacku totiž nemá qdrant kde
běžet.

Kontrola:

```
docker info > /dev/null 2>&1 && echo "funguje" || echo "OrbStack nebezi"
```

Musí to říct `funguje`. Když ne, počkej pár vteřin, až se OrbStack rozběhne, a
zkus znovu.

---

## 6. Ollama — embedding model

Ollama je program, který na tvém počítači spouští jazykové modely. Tady ji
potřebujeme jen k jedné věci: převádět kousky kódu na vektory.

```
brew install ollama
```

Aby se spouštěla automaticky po přihlášení:

```
brew services start ollama
```

Kontrola:

```
ollama list
```

Vypíše tabulku, nejspíš prázdnou. Prázdná je v pořádku — hlavní je, že to
nezahlásilo chybu. Model se stáhne až za chvíli, `agent-code-intel` si ho
dotáhne sám.

---

## 7. Node.js

Node.js je běhové prostředí pro JavaScript. GitNexus je v něm napsaný, takže bez
něj nepůjde nainstalovat. Zkontroluj, jestli ho už nemáš:

```
node --version
```

Když to vypíše číslo, jdi dál. Když ne:

```
brew install node
```

Kontrola:

```
node --version
npm --version
```

Obojí musí vypsat verzi.

### Verze Node.js musí být dost nová

Tohle je zrádné, protože stará verze se neprojeví hned. GitNexus se
nainstaluje, `gitnexus --version` bez potíží vypíše číslo, a teprve při
skutečném indexování to spadne na hlášce o `registerHooks`. Ověř si to rovnou:

```
node -e 'console.log(typeof require("node:module").registerHooks)'
```

Musí to vypsat `function`. Když vypíše `undefined`, je tvůj Node starý —
potřebná funkce přibyla v Node 22.15 a 23.5. Zjisti, odkud se ti Node bere:

```
which node
brew list --versions node
```

Podle výsledku jsi v jedné ze tří situací:

**Node je z Homebrew** — `brew list --versions node` vypsalo číslo:

```
brew upgrade node
```

**Node je z instalátoru z nodejs.org** — `which node` ukazuje do
`/usr/local/bin`, ale `brew list --versions node` nevypsalo nic. Tohle je
nejčastější případ a `brew upgrade node` v něm **selže** s hláškou
`Error: node not installed`, protože Homebrew ten Node nespravuje. Doinstaluj
si Homebrew verzi vedle:

```
brew install node
```

Na Apple Siliconu je `/opt/homebrew/bin` v PATH před `/usr/local/bin`, takže
nová verze tu starou rovnou zastíní; původní instalace zůstane nedotčená.
Ověř si to — `which node` už musí ukazovat do `/opt/homebrew`.

**Node je z nvm** — `which node` ukazuje někam do `.nvm`:

```
nvm install --lts
nvm use --lts
```

Po jakékoli změně verze Node.js **musíš GitNexus přeinstalovat**, protože je
navázaný na tu verzi, pod kterou se instaloval:

```
npm i -g gitnexus
```

---

## 8. GrepAI

GrepAI je ten nástroj, který dělá sémantické vyhledávání. Instaluje se z
vlastního repozitáře autora:

```
brew install yoanbernabeu/tap/grepai
```

Homebrew se během instalace může zeptat, jestli tomu repozitáři důvěřuješ.
Potvrď.

Kontrola:

```
grepai version
```

Musí vypsat číslo verze, například `grepai version 0.36.1`. Pozor, je to
`grepai version`, ne `grepai --version` — ten druhý tvar neexistuje a zahlásí
chybu.

---

## 9. GitNexus

GitNexus staví tu mapu vztahů v kódu.

```
npm i -g gitnexus
```

Vypíše pár varování o zastaralých balíčcích. To je v pořádku, jsou to varování,
ne chyby.

Kontrola:

```
gitnexus --version
```

Musí vypsat verzi.

> **Poznámka na později.** Pokud někdy budeš přepínat verze Node.js přes nvm,
> GitNexus po přepnutí přestane fungovat, i když ho `which gitnexus` pořád
> najde. Oprava je jednoduchá — `npm i -g gitnexus` pod novou verzí. Skript na
> to sám upozorní, protože GitNexus nekontroluje jen tím, že existuje, ale tím,
> že se opravdu spustí.

### Volitelný ripgrep (`rg`)

`rg` je rychlé přesné hledání textu. Routing skill ho volí tehdy, když už znáš
přesný identifikátor, konfigurační klíč, proměnnou prostředí nebo když chce po
úpravě ověřit výsledek. Pro samotné GrepAI a GitNexus není povinný.

```
brew install ripgrep
rg --version
```

---

## 10. agent-code-intel

Tento skript propojí vše uvedené výše do jednoho příkazu.

Soubor `agent-code-intel` uložte na dostupné místo, například do složky
Stažené. Poté v terminálu přejděte do dané složky a spusťte instalaci:

```
cd ~/Downloads
python3 ./agent-code-intel --install
```

Pokud je soubor uložený v podsložce, upravte cestu — například
`cd ~/Downloads/inteltest`.

Instalace udělá tři věci. Zkopíruje skript do `~/.local/bin/`, což je místo,
odkud se dá spouštět odkudkoli. Vytvoří konfiguraci v
`~/.config/code-intel/defaults.env`, kterou ti budoucí aktualizace nepřepíšou.
A přidá do nastavení Claude Code pravidlo, díky kterému nebude Claude muset žádat
o povolení pokaždé, když spustí `agent-code-intel --refresh`.

Jestli ti vypíše varování, že `~/.local/bin` není na PATH, spusť tohle:

```
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

Kontrola:

```
agent-code-intel --version
```

Musí vypsat číslo verze.

### Verze 4.1.0 a Python 3.11+

Verze 4 používá aktivní zdrojový launcher `agent-code-intel` a balík
`agent_code_intel/`. Vyžaduje Python 3.11 nebo novější. Launcher automaticky
nevybírá jiný interpret a při staré verzi skončí přesnou diagnostikou.
Při instalaci z checkoutu použijte aktuální `python3`, jehož verzi lze ověřit
příkazem `python3 --version`:

```
python3 ./agent-code-intel --install
```

Instalátor uloží tenký launcher do `~/.local/bin/agent-code-intel`, dashboard
do `~/.local/bin/code-intel-dash` a celý importovatelný balík do
`~/.local/lib/agent-code-intel/`. Instalace zkopíruje všechny Pythonové
moduly i dashboard, nepřenáší `__pycache__` a upgrade nahradí vlastní balík
jako celek. Verze dashboardu se čte z jeho vlastního `VERSION`; verze CLI
`4.1.0` ji nepřebíjí.

### Konfigurace: `defaults.env` a `defaults.toml`

Podporovány jsou dva formáty, ale v jednom běhu smí existovat právě jeden:

- `~/.config/code-intel/defaults.env` se vykoná skutečným Bashem. Zachovává
  expanze, odkazy na dříve nastavené hodnoty, pole, exporty i výstup na oba
  streamy; podporovaná konfigurace se předá podprocesům v neměnném prostředí.
- `~/.config/code-intel/defaults.toml` je typovaný soubor s deklarovanými
  klíči. Neprovádí shell ani expanzi proměnných. Neznámý klíč, chybný typ nebo
  neparsovatelný TOML je chyba.

Když neexistuje ani jeden soubor, instalace nabídne komentovanou TOML šablonu.
Existující ENV se automaticky nepřevádí do TOML a existující konfigurace se
nepřepisuje. Pokud existují oba soubory, nástroj skončí a vyžádá si ponechání
jednoho z nich.

### Ověření aktivního Pythonového launcheru

Aktivní vstup je po vydání kandidáta Pythonový launcher. Při ručním ověření
postupuj z checkoutu takto:

```
python3 ./agent-code-intel --version
python3 ./agent-code-intel --install
hash -r
command -v agent-code-intel
agent-code-intel --version
agent-code-intel --status --json
```

Zkontroluj, že `command -v` ukazuje do `~/.local/bin`. Konfigurace ENV zůstává
platná; převod do TOML je vždy ruční a volitelný.

---

## 11. První projekt

Teď to celé vyzkoušíme na testovacím projektu.

```
mkdir -p ~/projects/test-intel
cd ~/projects/test-intel
```

> **Pozor na velká písmena.** macOS nerozlišuje velikost písmen ve složkách, ale
> pamatuje si, jak jsi ji napsal. Když jednou napíšeš `~/Projects` a podruhé
> `~/projects`, dostaneš se do téže složky, ale ve Finderu pak hledáš něco, co
> se jmenuje jinak. Drž se jednoho tvaru, ideálně malých písmen.

Nejdřív si nech ukázat, co se stane, bez toho, aby se cokoli změnilo:

```
agent-code-intel
```

Skript nejdřív zkontroluje, jestli je všechno na svém místě, a přitom sám
nastartuje qdrant a ollamu, pokud neběží. Poprvé přitom stáhne image qdrantu a
embedding model, což je asi gigabajt — na chvíli se to zdánlivě zastaví, to je
v pořádku.

Pak vypíše seznam toho, co by udělal. Všechny řádky preflightu by měly být `ok`.

Když je vše zelené, spusť to naostro:

```
agent-code-intel --apply
```

Projde devíti kroky a na konci vypíše shrnutí. Ve složce ti přibudou tyhle
soubory:

| Soubor                                     | K čemu je                                             | Kdo ho vytvoří                       |
| ------------------------------------------ | ----------------------------------------------------- | ------------------------------------ |
| `.git/`                                    | Verzovací systém, založí se automaticky               | agent-code-intel                     |
| `.gitignore`                               | Aby se indexy nedostaly do gitu                       | agent-code-intel                     |
| `.grepai/`                                 | Nastavení indexování pro tenhle projekt               | agent-code-intel                     |
| `.mcp.json`                                | Napojení vyhledávání na tvého AI agenta               | agent-code-intel                     |
| `CLAUDE.md`                                | Odkaz na routing skill pro Claude                     | agent-code-intel pro `claude`/`both` |
| `.claude/skills/agent-code-intel-routing/` | Rozhoduje, kdy použít GrepAI, GitNexus nebo ripgrep   | agent-code-intel pro `claude`/`both` |
| `AGENTS.md`                                | Odkaz na routing skill pro Codex a ostatní agenty     | agent-code-intel pro `codex`/`both`  |
| `.agents/skills/agent-code-intel-routing/` | Stejný routing skill ve formátu, který objevuje Codex | agent-code-intel pro `codex`/`both`  |
| `.gitnexus/`                               | Grafový index a jeho databáze                         | gitnexus                             |
| `AGENTS.md`, `CLAUDE.md`                   | Vlastní oddělený blok s pravidly grafu                | gitnexus                             |
| `.claude/skills/gitnexus/`                 | Dovednosti pro Claude Code k práci s grafem           | gitnexus                             |

`--agent claude`, `--agent codex` a výchozí `--agent both` řídí současně MCP
registraci, dokument s instrukcemi i umístění routing skillu. GitNexus si při
`analyze` může navíc vytvořit vlastní bloky a Claude skilly bez ohledu na tuto
volbu; ty nejsou vlastnictvím `agent-code-intel`.

Umístění odpovídají oficiální dokumentaci pro
[Claude Code](https://code.claude.com/docs/en/skills) a
[Codex](https://learn.chatgpt.com/docs/build-skills).

Routing skill je záměrně verzovatelný: `.gitignore` pokrývá `.grepai/` a
`.gitnexus/`, ale ne `.claude/` ani `.agents/`. Tým tak dostane stejné
rozhodování nástrojů. Výchozí GrepAI konfigurace obě agentní složky při
indexování ignoruje.

Opakovaný `--apply` identický skill vůbec nepřepíše. Změněnou managed kopii
opraví automaticky; cizí skill stejného jména bezpečně odmítne. Pokud jej chceš
výslovně převzít pod správu nástroje, použij `--force-docs`. Přepínač
`--no-docs` přeskočí dokumenty i routing skilly.

---

## 12. Ověření, že to funguje

Vytvoř si testovací soubor. Otevři složku ve svém editoru — máš-li VS Code
s nainstalovaným příkazem `code`, stačí:

```
code .
```

Když `code` hlásí `command not found`, otevři složku ve VS Code přes
`File → Open Folder`, použij jiný editor, nebo si soubor vyrob rovnou
z terminálu:

```
cat > app.js <<'EOF'
function checkCredentials(user, pass) {
  const hash = hashPassword(pass);
  return db.users.findOne({ name: user, hash });
}
EOF
```

Do souboru `app.js` patří tohle:

```javascript
function checkCredentials(user, pass) {
  const hash = hashPassword(pass);
  return db.users.findOne({ name: user, hash });
}
```

Ulož ho. Pak zpátky v terminálu:

```
git add -A
git commit -m "prvni verze"
agent-code-intel --refresh
```

Commit dělej — je to dobrý zvyk a starší GitNexus ho pro vyhodnocení
aktuálnosti potřeboval. Od verze 1.6 už podmínka není: `gitnexus status` hlásí
`up-to-date` i v repozitáři bez jediného commitu. Takže když na něj zapomeneš,
nic se nerozbije.

Příkaz musí skončit hláškou `Code intelligence is fresh.`

### Tři kontroly

**Dostaly se vektory do databáze?**

```
curl -s http://127.0.0.1:6333/collections/workspace_test-intel | python3 -m json.tool | grep -iE "points|status"
```

Musíš vidět `"status": "green"` a `points_count` větší než nula.

**Funguje sémantické hledání?**

```
grepai search "overeni hesla uzivatele" --workspace test-intel
```

Musí najít `app.js`. Všimni si, že v tom souboru není ani slovo „ověření", ani
„heslo" — proto je tohle ten hlavní test. Obyčejný grep by nenašel nic.

Přepínač `--workspace` je povinný. Bez něj sáhne GrepAI po jiném, prázdném
indexu a vrátí nesmysly.

**Vidí to tvůj AI agent?**

Otevři složku v editoru a spusť v ní Claude Code. Napiš `/mcp` — musíš vidět
`grepai` i `gitnexus` jako připojené.

Když tam nejsou, nepotvrdil jsi při startu dialog, který se ptá, jestli
projektovým MCP serverům důvěřuješ. Zavři Claude Code, otevři znovu a potvrď.

Poslední test: zadej agentovi úkol, ve kterém nezmíníš název souboru ani funkce
— třeba „najdi, kde se v tomhle projektu ověřují přihlašovací údaje". Když
sáhne po nástroji `grepai_search`, je propojení kompletní.

---

## 13. Každodenní používání

### Nový projekt

```
mkdir ~/projects/muj-projekt
cd ~/projects/muj-projekt
agent-code-intel --agent claude --apply
```

To je celé. Nastavení, které jsi udělal jednou, platí pro všechny další
projekty.

### Po každé změně kódu

```
agent-code-intel --refresh
```

Tenhle příkaz by měl spouštět tvůj AI agent sám — instrukci k tomu má v
`CLAUDE.md` nebo `AGENTS.md`, který mu `agent-code-intel` napsal. Když to
neudělá, spusť ho ručně.

Proč je vůbec potřeba: GrepAI se aktualizuje průběžně, protože na pozadí běží
hlídač, který si všímá ukládaných souborů. GitNexus ne — jeho mapa se
přepočítává jen na povel, a právě tenhle příkaz ten povel dává. Zároveň
zkontroluje, že hlídač běží, a ohlásí, kdyby něco nesedělo. Kontroluje také
routing skill pro agenty vybrané přes `--agent`; jeho chybějící nebo změněná
kopie je drift a opraví ji další `--apply`.

Rychlá kontrola bez přeindexování:

```
agent-code-intel --status
```

### Kontrola všech projektů najednou

```
agent-code-intel --status --all
```

Projde všechny projekty, které jsi kdy nastavil, a řekne, kde něco nesedí.
Typicky po restartu Macu, kdy neběží hlídač.

### Po restartu počítače

OrbStack i ollama se spustí samy, pokud sis to nastavil v krocích 5 a 6.
**Hlídač GrepAI se ale sám nespustí.** Vyhledávání pak dál „funguje", jen
odpovídá ze zastaralých dat, což je horší než chyba. Pojistka je jednoduchá —
v projektu spusť:

```
agent-code-intel --refresh
```

Hlídače nastartuje a všechno doindexuje.

---

## 14. Dashboard — přehled o všem najednou

`agent-code-intel --status --all` ti řekne, jestli sedí _nastavení_ projektů.
Neřekne ti ale, jestli běží služby pod nimi a jestli opravdu dělají, co mají —
to je schválně, protože status musí fungovat i na stroji, kde je všechno
vypnuté.

Na tuhle druhou otázku odpovídá dashboard. Spusť ho:

```
code-intel-dash --open
```

Otevře se stránka na `http://127.0.0.1:7717`. Běží jen na tvém počítači, na
loopbacku, bez hesla — nikam se nedostane. Ukončíš ho Ctrl+C.

Instalace z checkoutu ho uloží vedle CLI automaticky:

```
python3 ./agent-code-intel --install
```

Při každé další instalaci se porovná vlastní verze dashboardu; shodná verze se
nepřepisuje, starší nebo poškozená kopie se nahradí zdrojovou verzí.

Dashboard nemá vlastní kontroly — všechno o projektech si vytáhne z
`agent-code-intel --status --all --json`. Kdyby měl kontroly vlastní, dřív nebo
později by se s tím příkazem rozešly a **oba by přitom dál svítily zeleně**.
Proto potřebuje `agent-code-intel` na PATH; bez něj rovnou řekne, že neví nic.

### Co na něm uvidíš

Nahoře **stack**, tedy věci společné všem projektům:

| Karta       | Co ověřuje                                                                  |
| ----------- | --------------------------------------------------------------------------- |
| docker      | běží daemon, běží kontejner, publikuje **oba** porty 6333 i 6334            |
| qdrant      | HTTP odpovídá, gRPC port je otevřený, kolik má kolekcí, jak rychle odpovídá |
| ollama      | server žije, model je stažený a načtený, **a skutečně vrátí vektor**        |
| Node.js     | verze, `registerHooks`, a jestli se gitnexus vůbec spustí                   |
| MCP servers | jestli běžící `gitnexus mcp` není starší než index — viz níže               |

Dole každý **projekt** ve čtyřech záložkách. Rozhraní dashboardu je anglicky:

- **Overview** — hlídač, počet vektorů, velikost grafu, stáří indexu,
  konfigurace. Když něco nesedí, je pod tím rovnou příkaz, který to spraví.
- **Search** — vlastní dotaz proti skutečnému indexu. Výsledky se dají
  rozklikávat: uvidíš cestu, rozsah řádků, skóre podobnosti a samotný úsek kódu
  s čísly řádků. Je to stejné hledání, jaké dostane agent.
- **Index contents** — které soubory se do indexu skutečně dostaly a kolik
  z nich zabírají. **Soubor, který tu chybí, hledání nikdy nenajde** — takhle
  se pozná tiché vypadnutí souboru z indexu.
- **Watcher log** — co hlídač poslední dobou dělal, indexační řádky zeleně.

Záložka se propíše do adresy (`#test-intel/search/...`), takže si konkrétní
pohled můžeš uložit do záložek nebo poslat dál.

### Proč to není jen „svítí zeleně"

Dashboard schválně netestuje jen to, že proces běží — to je slabé tvrzení.
U každé komponenty zkusí přímo to, kvůli čemu existuje:

- **ollama** dostane skutečný text k převedení na vektor. Když se vrátí 768
  čísel, je jistota, že embedding funguje; server, který odpovídá na `/api/tags`
  a přitom neumí embedovat, by jinak vypadal zdravě.
- **GrepAI** dostane skutečný dotaz. Nula výsledků znamená prázdný index, ne
  špatný dotaz.
- **qdrant** ukáže počet vektorů v kolekci. Zelená kolekce s nulou vektorů je
  rozbitý index, ne zdravý — dashboard to napíše červeně.
- **GitNexus** hlásí, pod jakou verzí Node byl index postavený. Když se
  neshoduje s tou, která běží teď, upozorní tě — to je přesně ta past
  z kapitoly 7.
- **MCP servers** porovná, kdy se spustil běžící `gitnexus mcp`, s tím, kdy byl
  balíček naposledy přepsaný. Node si totiž načte kód do paměti při startu
  procesu, takže po `npm i -g gitnexus` běží každý už otevřený agent dál na
  staré verzi. Nová `analyze` pak zapíše index, který ten starý server neumí
  přečíst, a uprostřed práce dostaneš `DB version mismatch, v43 index vs v42
MCP server`. Na disku není nic rozbité — jen je čtenář starší než soubor.
  Spraví to restart klienta a dashboard ti řekne, kterého.

Když je něco špatně, napíše rovnou příkaz, kterým se to spraví.

### Stáří údajů

Stránka se sama obnovuje každých 15 vteřin. Kdyby přestala, **zešedne a napíše,
že už za nic neručí** — protože dashboard, který po výpadku dál ukazuje poslední
zelený obrázek, je horší než žádný.

### Bez prohlížeče

Hodí se do skriptů, cronu nebo prompt řádku. Vypíše JSON a skončí s kódem 0 při
zdraví, 2 když je něco špatně:

```
code-intel-dash --once
```

Kdyby port 7717 kolidoval s něčím jiným:

```
code-intel-dash --port 8080
```

---

## 15. Když se něco pokazí

### `command not found`

Program buď není nainstalovaný, nebo systém neví, kde ho hledat. Vrať se ke
kroku, kde se instaloval, a zopakuj kontrolu. U `agent-code-intel` bývá příčinou
chybějící PATH — viz konec kroku 10.

### `docker run failed` nebo `Cannot connect to the Docker daemon`

OrbStack neběží. Spusť ho a počkej, až naběhne:

```
open -a OrbStack
sleep 15
docker info > /dev/null 2>&1 && echo "funguje" || echo "jeste ne"
```

Pak `agent-code-intel` spusť znovu.

### `embedding model ... not pulled` hned po úspěšném stažení

Server o modelu ještě neví. Prostě spusť příkaz znovu, podruhé projde.

### `grepai --version` hlásí `unknown flag`

Správný tvar je `grepai version`, bez pomlček.

### `does not provide an export named 'registerHooks'`

Tvůj Node.js je starý na to, co GitNexus potřebuje. Zákeřné na tom je, že
`gitnexus --version` funguje — rozbije se až samotné indexování. GrepAI to
neovlivňuje, sémantické hledání ti mezitím funguje dál.

Nejdřív zjisti, odkud se ti Node bere, protože oprava se podle toho liší:

```
which node
brew list --versions node
```

Pak postupuj podle **kapitoly 7**, sekce „Verze Node.js musí být dost nová" —
jsou tam popsané všechny tři případy. Pozor hlavně na ten nejčastější: když
`which node` ukazuje do `/usr/local/bin` a `brew list --versions node` mlčí,
je Node z instalátoru z nodejs.org a `brew upgrade node` selže na
`Error: node not installed`. Tam se používá `brew install node`.

Po jakékoli změně verze Node.js je přeinstalace GitNexusu povinná:

```
npm i -g gitnexus
```

Pak v projektu:

```
agent-code-intel --refresh
```

### `workspace ... does not map this project`

Cesta uložená v GrepAI neodpovídá té, ze které skript běží. Nejčastěji kvůli
velkým písmenům — `~/Projects` versus `~/projects`. Zjisti skutečný tvar:

```
cd ~/projects/muj-projekt
pwd -P
```

Používej ten, který ti to vypsalo.

### Ve složce „nejsou" `.mcp.json` a `CLAUDE.md`

Skoro jistě jsi v jiné složce, než si myslíš. Ověř:

```
pwd -P
ls -la
```

Ve VS Code otevři složku přes `File → Open Folder` přímo na projekt, ne na
nadřazený adresář. Nebo rovnou z terminálu:

```
cd ~/projects/muj-projekt && code .
```

### V Claude Code chybí nástroje grepai a gitnexus

Napiš `/mcp` a podívej se, co je připojené. Když tam nejsou, zavři Claude Code a
otevři znovu ve složce projektu — při startu se ptá, jestli projektovým MCP
serverům důvěřuješ, a ten dialog je potřeba potvrdit.

### Vyhledávání vrací nesmysly nebo nic

Projdi to v tomhle pořadí:

1. Běží hlídač? `grepai watch --workspace NAZEV --status`
2. Jsou v databázi vektory? Viz kontrola v kapitole 12.
3. Zapomněl jsi `--workspace`? Bez něj hledá GrepAI v prázdném indexu.
4. Co dělá hlídač? `tail -20 ~/Library/Logs/grepai/grepai-workspace-NAZEV.log`

### Nikdy neupravuj `.grepai/config.yaml` ručně

Tenhle soubor si hlídač drží v paměti a při každém indexování ho **celý
přepíše**. Tvoje úprava zmizí — bez chyby, bez záznamu v logu, klidně až za pár
hodin. Když potřebuješ něco změnit, uprav `~/.config/code-intel/defaults.env` a
spusť `agent-code-intel --apply` znovu.

---

## 16. Odinstalace

### Jeden projekt

Ve složce projektu:

```
agent-code-intel --remove
```

Ukáže, co by smazal. Když souhlasíš:

```
agent-code-intel --remove --apply
```

Odpojí projekt, zastaví hlídač, smaže vygenerované soubory, vyřízne managed
instrukce z `CLAUDE.md` a `AGENTS.md` a odstraní obě managed kopie routing
skillu. Cizí skill stejného jména zachová. Tvého kódu ani gitu se nedotkne.
Chceš-li smazat i vektory z databáze, přidej `--purge-collection`.

### CLI bez smazání konfigurace

Nejdřív si případně zazálohuj nastavení. Odstranění CLI je oddělené od projektů,
registru a sdíleného stacku:

```
rm -f ~/.local/bin/agent-code-intel
rm -rf ~/.local/lib/agent-code-intel
```

`~/.config/code-intel` nemaž, pokud chceš zachovat konfiguraci a registr pro
pozdější instalaci. Soubor `~/.claude/settings.json` také nemaž celý: pokud
chceš odstranit automatické povolení, odeber pouze přesné pravidlo
`Bash(agent-code-intel --refresh)` a zachovej ostatní oprávnění.

### Volitelné odstranění konfigurace a registru

Po kontrole obsahu můžeš odstranit pouze data tohoto nástroje:

```
rm -rf ~/.config/code-intel
```

Tohle nemaže žádný projektový zdroj ani Qdrant data. Projekty je nutné nejdřív
odpojit příkazem `agent-code-intel --remove --apply`; kolekci smaž jen při
samostatném, výslovném použití `--purge-collection`.

### Celý stack

```
rm ~/.local/bin/agent-code-intel
rm ~/.local/bin/code-intel-dash
rm -rf ~/.config/code-intel
brew uninstall grepai
npm uninstall -g gitnexus
docker rm -f grepai-qdrant
docker volume rm grepai-qdrant-data
brew services stop ollama
brew uninstall ollama
brew uninstall --cask orbstack
```

Homebrew, Node.js a stažený model si nech, pokud je používáš i k jinému.

---

## 17. Slovníček

**Embedding, vektor** — převod textu na sadu čísel, která zachycuje význam. Dva
texty o témže mají podobná čísla, i když nemají společné slovo.

**Sémantické vyhledávání** — hledání podle významu místo podle přesného textu.
To, co dělá GrepAI.

**Kontejner** — izolované prostředí pro jeden program. Nemusíš ho instalovat do
systému, jen ho spustíš a případně zase zahodíš.

**Image** — předpis, ze kterého se kontejner vytvoří. Stahuje se jednou.

**Hlídač, watcher** — program běžící na pozadí, který sleduje ukládané soubory a
průběžně je doindexovává.

**Index** — datová struktura pro rychlé hledání. Tady jsou dva: vektorový v
GrepAI a grafový v GitNexusu.

**MCP** — způsob, jakým se k AI agentovi připojují externí nástroje. Díky němu
umí Claude Code volat GrepAI a GitNexus.

**PATH** — seznam složek, kde systém hledá programy. Když v něm složka není,
musíš program spouštět celou cestou.

**Workspace** — pojmenovaná skupina projektů v GrepAI. Tenhle stack zakládá
jeden workspace na projekt.

**Preflight** — kontrola před startem. Zjistí, co chybí, a vypíše to všechno
najednou.

**Idempotentní** — vlastnost příkazu, který můžeš spustit vícekrát a výsledek je
stejný. `agent-code-intel --apply` proto můžeš spouštět opakovaně; co je hotové,
nechá být, co se rozpadlo, opraví.
