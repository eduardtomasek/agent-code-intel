# Zadání pro Wayfinder: migrace agent-code-intel z Bashe do Pythonu

Použij `/wayfinder` v režimu **Chart the map** pro níže popsaný záměr. Tento dokument je vstupní zadání, nikoli hotová specifikace ani pokyn k implementaci. Komunikuj česky.

## Destination

Najít a doložit cestu k migraci hlavního CLI `agent-code-intel` z Bashe na Python 3.11+ se standardní knihovnou, zachováním dohodnutého vnějšího chování a jednoduchou samostatnou instalací. Mapa je dokončená, až lze bez dalších zásadních rozhodnutí vytvořit implementační specifikaci a následně rozdělit práci na ověřitelné implementační kroky.

Výstup Wayfinderu tvoří rozhodnutí, jejich zdůvodnění, důkazy, závislosti a kritéria ověření. Samotný přepis programu je až následná práce. V této etapě neupravuj produkční kód, konfiguraci uživatele, běžící služby ani indexy. Zkoušky, které by něco z toho vyžadovaly, nejprve navrhni jako samostatné ověření k odsouhlasení.

## Notes: jak s tímto zadáním pracovat

- Řiď se dostupným skillem Wayfinder a platnými instrukcemi repozitáře. Skill je nyní dostupný v `/Users/eddy/.agents/skills/wayfinder/SKILL.md`; v jiné relaci ověř jeho skutečnou dostupnost.
- Použij `code-intelligence-routing` pro průzkum a `karpathy-guidelines` pro návrh. Doménovou terminologii ověř podle `docs/agents/domain.md`; pro rozhovor použij dovednosti vyžadované Wayfinderem.
- Nejprve ověř současnou implementaci. Každé významné tvrzení o jejím chování opři o soubor/symbol, test nebo ověřený výsledek. Rozlišuj současné chování, odsouhlasený požadavek, návrh a neověřenou hypotézu.
- Už odsouhlasená rozhodnutí níže použij jako výchozí omezení. Znovu je otevírej pouze při doloženém konfliktu a vysvětli konkrétní důvod.
- Otázky zodpověditelné čtením kódu nebo dokumentace prozkoumej sám. Uživatele zapoj do skutečných voleb chování, kompatibility a rozsahu. Nevydávej vlastní doporučení za uživatelovo rozhodnutí.
- Použij GitHub tracker podle `docs/agents/issue-tracker.md`, včetně jeho sekce Wayfinding operations. Ověř existující mapy, štítky a dostupnost vztahů před vytvořením nové mapy. Uživatelské odkazy pojmenovávej názvy issues.
- Toto zadání opravňuje při jeho budoucím spuštění vytvořit plánovací mapu, její rozhodovací issues a vztahy v nakonfigurovaném trackeru. Nevytvářej implementační issues místo rozhodovacích otázek.
- V této etapě nevytvářej gitové branche, commity, tagy ani PR. Toto omezení platí také pro research subagenty: jejich zjištění patří do plánovacích podkladů a rozhodovacích issues, ne na novou research branch. Pokud je deleguješ podle Wayfinderu, předej jim tato omezení.
- Dodrž hranice jednotlivých relací Wayfinderu. Po zmapování nepokračuj automaticky do implementace ani nevyřeš všechny lidské rozhodovací otázky za uživatele. Příprava specifikace je následný handoff.
- Při chybějícím nutném kontextu nebo neplatné konfiguraci trackeru vrať konkrétní `[ERROR: důvod]`. Záměrně otevřené návrhové otázky tohoto zadání jsou práce pro mapu, nikoli důvod k ukončení mapování.

## Motivace a dosavadní dohoda

Projekt začal jako shellová orchestrace, ale nyní obsahuje více režimů, strukturovanou konfiguraci, migrace, kontroly stavu, správu procesů a řadu vložených Pythonových bloků. Uživatel chce přehlednější řízení programu a lepší testovatelnost při zachování funkčnosti.

### Odsouhlasená rozhodnutí

1. **Python 3.11 nebo novější.** Používej pouze standardní knihovnu pro běh programu i povinné testy. Požadavek 3.11 má konkrétní důvod: vestavěný `tomllib`. Nenavyšuj minimum kvůli pohodlnější syntaxi nebo API, pokud ekvivalent v 3.11 existuje. Novější podporované verze ověř testy; jejich kompatibilitu pouze nepředpokládej.
2. **Několik účelných Pythonových modulů.** Odděl odpovědnosti podle zjištěného chování. Nevytvářej framework, pluginový systém ani univerzální workflow engine. Názvy modulů, jejich počet a rozhraní nejsou zatím rozhodnuté.
3. **Instalace jedním příkazem.** Navržený a přijatý vstup je `python3 ./agent-code-intel --install` ze staženého repozitáře. Změna původního `bash` na `python3` je výslovně povolená. Zachování příkazu spouštěného přes Bash není požadavek.
4. **Samostatná instalace mimo zdrojový checkout.** Program se kopíruje do `~/.local/lib/agent-code-intel/`; v `~/.local/bin/agent-code-intel` bude tenký spustitelný Pythonový vstup. Stažený repozitář lze po instalaci přesunout či smazat. K běhu nesmí být potřeba původní pracovní adresář, gitový checkout, vývojové nástroje ani doplňování `PYTHONPATH` uživatelem.
5. **Bez pip, venv a externích Pythonových balíčků.** Stávající externí nástroje stacku zůstávají samostatnými provozními závislostmi. Cílem není přepsat GitNexus, GrepAI, Ollamu nebo kontejnerový runtime do Pythonu.
6. **Vnější kompatibilita.** Zachovat existující příkazy, přepínače, význam jejich kombinací, výchozí chování, návratové kódy, strojové JSON výstupy, identitu projektů, data, ochrany ručních úprav a relevantní pořadí vedlejších účinků. Detailní hranice textové kompatibility a konkrétní výjimky musí být ještě uzavřeny v mapě.
7. **TOML jako cílový formát uživatelské konfigurace.** Pro načítání použít `tomllib`. Instalátor může vytvořit komentovanou statickou šablonu; aktualizace nesmí přepsat uživatelovy hodnoty. Není schválen vlastní obecný TOML serializer ani externí knihovna pro zápis.
8. **Stávající `defaults.env` musí zůstat funkční.** Zachovat kompatibilní shellové načítání přes Bash. Automatický obecný převod vykonatelného shellového souboru na statický TOML není součástí dohody. Přesný přechod a souběh formátů je otevřená otázka níže.
9. **Dashboard zůstává mimo přepis a změnu instalace.** `code-intel-dash` už je Pythonový. Zachovat jeho samostatnou instalaci a kompatibilitu se strojovým výstupem hlavního CLI. Nezavádět společné balení ani sdílené moduly vyžadující změnu dashboardu bez nového rozhodnutí.
10. **Ověření třemi vrstvami.** Zachovat současné CLI testy jako nezávislou kontrolu, přidat jednotkové testy skutečného chování a ověřit integrace na reálném stacku. Srovnání Bash/Python má být hlavním důkazem kompatibility, nikoli jen podobnost kódu.

## Zdrojový kontext, který ověř

Výchozí pracovní adresář při sepsání zadání: `/Users/eddy/Work/Personal/agent-code-intel`.

- `agent-code-intel`: hlavní Bash CLI. Čti celý relevantní tok, ne jen nápovědu; obsahuje vložený Python a záměrné výjimky v zacházení s chybami.
- `code-intel-dash`: konzument `agent-code-intel --status --all --json`. Ověř přesný datový kontrakt a způsob spouštění CLI.
- `test/run.sh`: existující izolované CLI testy, možnost nastavit `TOOL`, popsané trvalé mezery pokrytí.
- `README.md`: uživatelské postupy instalace, aktualizací, používání a odinstalace.
- `CHANGELOG.md`, `TESTreport.md` a relevantní dřívější issues/rozhodnutí: zdroje kompatibility a dřívějších kompromisů. Rozlišuj historické informace od aktuální implementace.
- `AGENTS.md`, případné hlubší instrukce a `docs/agents/`: pravidla práce, doména a tracker.

Před porovnáváním implementací navrhni způsob zachování přesně identifikovaného Bashového referenčního stavu. Žádný commit ani větev pro tento účel nejsou nyní povolené. Reference musí zůstat použitelná i po nahrazení souboru Pythonovým vstupem.

Externě ověřené výchozí zdroje:

- `tomllib` je součástí Pythonu od 3.11 a neumí zapisovat TOML: https://docs.python.org/3/library/tomllib.html
- Dostupná standardní knihovna: https://docs.python.org/3.11/library/
- Stav podpory verzí, který je potřeba vztáhnout k datu návrhu: https://devguide.python.org/versions/
- Specifikace TOML: https://toml.io/en/v1.0.0
- Dostupnost Pythonu na macOS není zárukou vhodné verze: https://docs.python.org/3/using/mac.html

## Otevřené rozhodovací oblasti

Následující oblasti nejsou hotové implementační tickets. Použij je k rozhovoru napříč rozsahem a sestavení rozhodovací mapy. Přesné otázky lze založit i jako blokované; pouze dosud neformulovatelnou nejistotu ponech v Not yet specified.

### A. Co přesně je kompatibilní výsledek?

Vytvoř inventář všech režimů a přepínačů podle aktuálního parseru. Pro každý zachyť vstupy, výchozí hodnoty, validační pořadí, stdout/stderr, návratové kódy, vedlejší účinky a závislosti potřebné právě pro tento režim.

Rozhodni s uživatelem:

- Musí být textové výstupy a diagnostika stejné znak po znaku, nebo lze měnit formulaci a formát při zachování významu? Doporučení pro začátek: během migrace držet současné texty tam, kde není nutná schválená změna, a redesign výpisů oddělit.
- Jak evidovat zjištěný rozpor mezi dokumentací, testem a chováním? Každou odchylku klasifikovat jako zachovaný kontrakt, schválenou změnu nebo samostatnou chybu; nespravovat ji potichu při přepisu.
- Které rozdíly jsou nevyhnutelně povolené kvůli novému instalátoru, minimální verzi Pythonu a cílovému konfiguračnímu formátu?

Zvlášť ověř parsování opakovaných a konfliktních přepínačů a rychlé ukončení přes `--help`/`--version`. Výchozí chování `argparse`, například návratový kód při chybě, se nesmí automaticky stát novým kontraktem.

### B. Jak přejdeme z defaults.env na TOML bez ztráty chování?

Zjisti všechny konfigurací ovlivnitelné hodnoty, včetně seznamů, cest, odvozených hodnot a jejich precedence. Současný soubor se vykonává přes `source`; shellový subprocess s předáním několika proměnných není bez další analýzy úplným ekvivalentem.

Rozhodni zejména:

- Název a schéma TOML, typy hodnot, sekce, pravidla pro neznámé klíče a neplatné hodnoty. Názvy a struktura z předchozího ilustrativního příkladu nejsou závazné.
- Kdy TOML začne vznikat: pouze nové instalace, explicitní přechod, nebo samostatná následná etapa? Podpora TOML je odsouhlasená, přesné nasazení zatím není.
- Co nastane při existenci jen ENV, jen TOML, obou souborů nebo žádného? Vyžaduje souběh explicitní volbu, pevnou prioritu, nebo je chybou? Automatické slučování není schválené.
- Jak zabránit tomu, aby aktualizace vytvořením nového souboru zastínila starou funkční konfiguraci?
- Co znamená kompatibilita ENV pro expanze, pole, exportované proměnné, relativní cesty, pracovní adresář, výstup na stdout/stderr, chyby při načítání a další shellové účinky? Rozliš doloženou podporovanou konfiguraci od libovolného programování uvnitř souboru; případné omezení musí uživatel výslovně přijmout.
- Jak přenášet hodnoty z kompatibilního Bashového načítání do Pythonu bez ztráty znaků a bez logování celého prostředí? Nečti ani nevypisuj skutečné uživatelské secrets; navrhuj nad kontrolovanými příklady.
- Jak zachovat `XDG_CONFIG_HOME`, projektovou identitu `.code-intel` a existující registr? TOML pro uživatelské defaults automaticky neznamená změnu těchto dalších formátů ani cizích YAML/JSON/TOML konfigurací.

Definuj výslovně, že statický TOML sám nevykonává shellové expanze; pokud by mělo existovat doplňování proměnných nebo `~`, jde o další chování k rozhodnutí, ne samozřejmost.

### C. Jak bude instalace a aktualizace fungovat jako celek?

Umístění instalace a Pythonový vstup jsou rozhodnuté. Zbývá navrhnout jejich životní cyklus:

- Které moduly a datové soubory patří do instalace a jak je obě varianty spuštění — ze zdrojů a nainstalovaná — spolehlivě najdou?
- Jak funguje první instalace, opakovaná instalace, přechod ze současné Bashové instalace a `--install` spuštěné z již nainstalovaného programu?
- Jak se vybírá interpret při běžném běhu a jak se projeví změna PATH nebo přesunutí Pythonu? Ověř kompromis mezi `env python3` a jiným výběrem; nepřipoutávej řešení k vývojářskému stroji.
- Jak včas ověřit Python 3.11+ a ukončit instalaci před změnami, pokud požadavek není splněný? Vstup musí stihnout vypsat srozumitelnou chybu před importem modulů závislých na 3.11.
- Jak aktualizace zabrání směsi starých a nových modulů, jak naloží s odstraněnými moduly a co zůstane funkční při neúspěšném kopírování nebo přerušení? Navrhni nejmenší dostatečné řešení; obecný správce verzí není cílem.
- Jak se zachová existující konfigurace, upozornění na PATH, starý název `code-intel-init`, přesné Claude permission pravidlo, `--no-perms` a upozornění na samostatnou aktualizaci dashboardu?
- Jaký je úplný návod na odstranění nově instalovaných souborů? Odliš od projektového `--remove`; nový přepínač `--uninstall` není schválený.

Povinný budoucí akceptační scénář: instalovat do izolovaného uživatelského prostředí, přesunout či odstranit zdrojovou kopii a spustit nainstalovaný příkaz z jiného pracovního adresáře. Pythonové moduly se nesmějí omylem načíst ze zdrojového checkoutu.

### D. Kde povedou hranice modulů a vedlejších účinků?

Navrhni malý počet modulů na základě skutečných odpovědností. Kandidáti k posouzení jsou vstup/CLI, konfigurace a identita, kontroly externích nástrojů, operace nad soubory, orchestrace režimů a instalace. Nejde o předepsaný seznam souborů.

Rozhodni předávání stavu bez spleti měnitelných globálních proměnných, společné reprezentace výsledků kontrol, hranici výjimek vůči CLI návratovým kódům a místo pro parsování výstupů cizích CLI. Import modulů musí být bez provádění CLI, spouštění služeb a změn souborů.

Odděl rozhodování od I/O tam, kde to zlepšuje ověření chování. Zachovej jediný zdroj kontrol používaných více režimy. Nový model plánu nesmí omylem zavést atomické chování nebo přeuspořádat operace, které dnes atomické nejsou.

Zhodnoť běh procesů na pozadí, timeouty, signály a přenos výstupů. Nové timeouty nebo nové ukončování podprocesů mohou měnit chování a vyžadují zdůvodnění. Není důvod předem předepisovat asyncio, paralelní provádění nebo procesní framework.

### E. Které zvláštnosti integrací musíme zachovat?

Ověř v implementaci a zahrň do kontraktu:

- Preview může při preflightu bootstrapovat infrastrukturu. Nelze pro celý nástroj předpokládat, že absence `--apply` znamená absolutně žádné vedlejší účinky. Odliš preview inicializace, status, JSON status a dry-run odstranění.
- `--refresh` vyžaduje existující `.code-intel`, hledá nejbližší git root, respektuje explicitní `--path` a nesmí adoptovat identitu nadřazeného repozitáře přes hranici vnořeného repa.
- Precedence explicitního workspace, `.code-intel`, registru a odvození názvu; kanonizace cest a validační chyby identity. `.code-intel` se nikdy nevykonává jako shell.
- Kontroly HTTP i gRPC Qdrantu, správný workspace a embedding model, konflikt stejného názvu projektu s jinou cestou a existující logika bootstrapu.
- Generovaný GrepAI YAML, zachování okolního obsahu a restart watcheru po relevantní změně, aby změnu nepřepsal stav z paměti. Nepřidávat vlastní obecný YAML parser.
- Rozdílné scope a jména MCP registrací Claude/Codex, upozornění na nesprávný globální GrepAI a registrace GitNexusu podle názvu místo nestabilní absolutní cesty.
- Vlastnictví a hranice generovaných bloků v dokumentech, soubory vytvářené GitNexusem, ignorované soubory a opakované spuštění.
- Migrace legacy `refresh-intel.sh`, kontrola razítka/hash, převzetí identity a ochrana ručních úprav. Nový přepis nesmí znovu zavést odstraněné veřejné rozhraní.
- Záměrně tolerované chyby a pokračování po selhání analýzy. Ověř také konkrétní fallback při chybě „Embedding generation completed without persisted embeddings“ a jeho dopad na následný audit.
- `--remove`, `--purge-collection`, ochrana ručních změn a oddělení odstranění projektu od instalace nástroje.
- Přesné schéma a exit status JSON režimu nezávisle na textovém statusu. Nevyvozuj univerzální návratové kódy ze souhrnu v nápovědě; ověř dispatch i konzumenta v dashboardu.

### F. Jak prokážeme kompatibilitu a dokončení?

Navrhni akceptační matici: scénář → referenční chování → způsob ověření → prostředí → důkaz výsledku. Každý režim, schválená odchylka a výše uvedený invariant musí mít ověření nebo konkrétní přiznanou mezeru.

Požadavky na strategii:

- Současnou Bashovou testovací sadu použít proti oběma implementacím. Nepřepisovat zároveň očekávání podle nového kódu. Prozkoumat její izolované PATH, protože nalezený systémový Python nemusí splnit 3.11+.
- Jednotkové testy v `unittest`: parsování konfigurací, identita, rozhodování o stavu, zachování cizího obsahu, precedence a chybové stavy. Testovat pozorovatelné chování, ne mechanicky každou pomocnou funkci.
- Srovnávat výsledky na oddělených, ekvivalentních fixturech. Dvě mutující implementace neběží po sobě nad stejným již změněným stavem. Stejně oddělit workspace, registry, domovy a zdroje reálného stacku.
- U diferenciálních výsledků porovnat návratové kódy, stdout/stderr, JSON, relevantní soubory a účinky. Normalizace času a dočasných cest musí být explicitní a nesmí schovat skutečné rozdíly.
- Skutečné integrace ověřit na stacku. Dnešní sada záměrně nemá úplný happy-path pro apply/preview a drift refresh; tuto mezeru nezaměnit za důkaz správnosti. Respektovat existující rozhodnutí nevytvářet rozsáhlé imitace cizích CLI; případnou změnu této strategie zvlášť projednat.
- Ověřit funkční stav, drift, chybějící nástroje/služby, prázdné a poškozené konfigurace, opakované spuštění, ručně upravené soubory a relevantní selhání uprostřed operace.
- Ověřit prvotní instalaci, upgrade z Bashe, další Pythonový upgrade, konfiguraci v nestandardním XDG adresáři, cesty s mezerami/Unicode a nezávislost na checkoutu.
- Navrhnout konkrétní matici macOS/Linux, architektur a podporovaných Pythonů. Minimum 3.11 je rozhodnuté; konkrétní distribuce, verze OS a dostupná testovací prostředí ještě nejsou. Rozliš slíbenou podporu a skutečně ověřené kombinace.
- Nové jednotkové/CLI testy musí být spustitelné bez skutečného stacku. Rozhodni, kde a jak spouštět integrace; nepřidávej stack do závislostí či CI cizích projektů, které nástroj pouze indexuje.

### G. Jak migraci rozdělit a předat k realizaci?

Rozhodni posloupnost, která umožňuje průběžné porovnávání: referenční kontrakt a testovací podklady, hranice modulů, převod režimů, instalace a konfigurace, konečné integrační ověření. Toto pořadí je návrh k posouzení, nikoli schválený seznam implementačních tasks.

Urči, jak dlouho budou obě implementace dostupné pro ověřování, jak se provede konečné přepnutí a co musí být splněno před odstraněním referenční kopie. Rozhodni nutné změny dokumentace a oznámení požadavku na Python 3.11+ a nového instalačního příkazu.

Mapu uzavři odkazovanými rozhodnutími a jasným předáním do specifikace. Samotné vytvoření souboru se specifikací, rozpad na implementační issues nebo zahájení kódování nejsou automatickým pokračováním tohoto zadání.

## Out of scope

- Implementace migrace během mapování, provozní opravy stroje a refresh indexů jen kvůli plánování.
- Nové produktové funkce, redesign CLI a dashboardu, nové backends nebo změna používaných embedding modelů.
- Přepis nebo náhrada externích nástrojů; odstranění všech systémových závislostí.
- Windows podpora, pokud uživatel později výslovně nerozšíří rozsah.
- Distribuce přes PyPI, Homebrew, pipx, kontejnery nebo binární bundlery; automatické stahování Pythonu a samostatný síťový auto-updater.
- Společná instalace dashboardu a hlavního CLI.
- Plošný převod všech stavových a cizích konfiguračních souborů na TOML.
- Tichá oprava existujících chyb nebo omezení podporované konfigurace pod označením „refaktor“.

## Kritéria dokončení mapy

Mapa je připravená k předání, až:

1. Máme ověřený inventář veřejného chování a vedlejších účinků, včetně výjimek a známých rozporů.
2. Každá navržená odchylka od současného chování je buď výslovně schválená, nebo vyřazená z migrace.
3. Je rozhodnutá přesná koexistence ENV/TOML, precedence, validační pravidla a rozsah shellové kompatibility.
4. Je popsán celý životní cyklus instalace a aktualizace bez závislosti na zdrojovém repozitáři.
5. Hranice modulů, stav a chyby lze popsat konkrétními odpovědnostmi a testovatelnými rozhraními bez spekulativní infrastruktury.
6. Každý zachovávaný režim a kritický invariant má přiřazený způsob ověření; dostupnost reálných prostředí a zbývající omezení jsou vyřešené, ne skryté za zelenými unit testy.
7. Je rozhodnutá posloupnost migrace, reference pro porovnávání, podmínky přepnutí a dokumentace.
8. Nezbývá otevřená zásadní volba blokující napsání specifikace. Běžné implementační detaily mohou zůstat vývojáři; nerozhodnutý kontrakt nebo nedostupné povinné ověření běžným detailem není.

Pro první relaci nejprve stručně potvrď porozumění destination a odsouhlaseným omezením. Poté s uživatelem otevři skutečné zbývající volby, sestav mapu podle Wayfinderu a skonči na hranici režimu Chart the map.
