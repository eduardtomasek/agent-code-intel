# Podpora Windows: research, analýza a plán

- **Stav:** návrh s rozhodnutími z 2026-09-17 (kapitola 10). Všechny otázky
  Q1–Q16 jsou rozhodnuté; několik mechanismů ještě ověří fáze 0.
  Nic z tohoto dokumentu není implementováno.
- **Výchozí verze:** agent-code-intel 6.2.0 (commit `f552b0f`).
- **Datum průzkumu:** 2026-09-17.
- **Cíl:** `agent-code-intel` (CLI, instalátor, `--install-deps`, `--apply`,
  `--refresh`, `--status`, `--remove`) a `code-intel-dash` fungují na nativním
  Windows stejně jako na macOS. Systém se detekuje automaticky a každá platforma
  má vlastní instalační cestu.

## Jak číst tento dokument

Každé důležité tvrzení má značku původu:

| Značka | Význam |
| --- | --- |
| **[ověřeno: S*n*]** | Ověřeno v primárním zdroji ze sekce [Zdroje](#14-zdroje). |
| **[kód: soubor:řádek]** | Ověřeno čtením kódu tohoto repozitáře ve verzi 6.2.0. |
| **[odvozeno]** | Logický závěr ze dvou a více ověřených faktů. Není otestováno na Windows. |
| **[neověřeno]** | Nepodařilo se ověřit v primárním zdroji. Před implementací nutno ověřit. |

Žádné tvrzení nebylo otestováno na skutečném stroji s Windows. Průzkum proběhl
na macOS čtením zdrojů, release artefaktů a dokumentace. Proto plán začíná
fází, která ověří nejrizikovější předpoklady na reálném Windows.

> **Agent na Windows 11, který má ověřit tento plán:** přečti kapitoly 1–14
> jako kontext a pak proveď
> [kapitolu 15, runbook fáze 0](#15-fáze-0-runbook-pro-agenta-na-windows-11)
> krok po kroku.

---

## 1. Shrnutí

**Závěr:** Nativní podpora Windows je proveditelná. Každá povinná komponenta
stacku má nativní Windows build. Žádná ale není „drop-in“: kód dnes na několika
místech předpokládá POSIX a macOS, a to rozbije většinu režimů.

Hlavní zjištění:

1. **Všechny povinné nástroje existují pro Windows x64.** Jde o grepai, qdrant,
   Ollama, Node.js, GitNexus, Python, Git, Claude Code i Codex. Viz
   [kapitola 4](#4-průzkum-nástrojů-na-windows).
2. **OrbStack na Windows není.** Náhrada je Docker Desktop (WSL 2 backend),
   Docker Engine uvnitř WSL 2, Podman Desktop nebo Rancher Desktop. Qdrant má
   navíc **nativní Windows binárku**, takže kontejner není na Windows nutný
   [ověřeno: S1]. **Rozhodnuto:** na Windows poběží **nativní `qdrant.exe`**,
   bez Dockeru a bez WSL (kapitola 6.12). Qdrant má licenci Apache-2.0, NTFS
   označuje za podporovaný souborový systém a testuje se na Windows v CI
   [ověřeno: S27]. Docker Desktop je pro větší firmy placený [ověřeno: S12] a
   WSL ve výchozím nastavení vypíná nečinnou distribuci [ověřeno: S25]; proto
   byly obě cesty zamítnuty.
3. **Největší technický blokátor je spouštění npm nástrojů.** `gitnexus` je na
   Windows `.cmd` shim. `subprocess.run(["gitnexus", …])` ho nenajde, protože
   `CreateProcess` doplňuje jen `.exe` [ověřeno: S20]. Současně
   `shutil.which("gitnexus")` ho najde přes `PATHEXT`. Preflight tedy řekne
   „on PATH“, ale volání skončí kódem 127 [kód: integrations.py:46–63, :111–113;
   odvozeno].
4. **Instalátor vytváří soubor bez přípony se shebangem**
   [kód: install.py:312]. Windows shebang nečte, takže `agent-code-intel` by
   nešel spustit z PowerShellu ani z CMD [odvozeno].
5. **Hooky a skills předpokládají shell `sh`/`bash`.** Claude Code na Windows
   spouští hooky přes Git Bash, a bez Git Bash přes PowerShell [ověřeno: S15].
   Codex má pro Windows zvláštní pole `commandWindows` [ověřeno: S17].
6. **Dashboard je vázaný na macOS.** Používá `ps -eo`
   [kód: code-intel-dash:197] a cestu k logům `~/Library/Logs/grepai`
   [kód: code-intel-dash:426–429]. Na Windows píše grepai logy do
   `%LOCALAPPDATA%\grepai\logs` [ověřeno: S3].
7. **Windows ARM64 nelze v první verzi podporovat.** GitNexus závisí na
   `@ladybugdb/core`, který má prebuild jen pro `win32-x64`
   [ověřeno: S6]. Proto na Windows ARM64 GitNexus pravděpodobně nepůjde
   [odvozeno].
8. **Tři nástroje z vrstvy code-context mají slabou podporu Windows.** `tokei`
   nemá Windows binárky v releasech v13–v15 [ověřeno: S10]. `rga` má poslední
   Windows build ve verzi 0.10.9 [ověřeno: S11]. `scc` nemá balíček ve winget
   pod ověřenými ID [neověřeno, viz 4.7]. Všechny tři jsou jen „strongly
   recommended“, takže nejsou blokující.

**Doporučení a rozhodnutí:**

- Strategie **A: nativní Windows x64** (kapitola 7), včetně qdrant.
- qdrant na Windows: **nativní `qdrant.exe`** jako proces uživatele, poslouchá
  jen na `127.0.0.1`, s připnutou verzí. Na Windows není potřeba žádný
  kontejnerový runtime. macOS zůstává u kontejneru.
- Instalace do `%USERPROFILE%\.local\bin` a `%USERPROFILE%\.local\lib`,
  konfigurace v `%USERPROFILE%\.config\code-intel`. Spouštění přes `.cmd` shim.
- **Git for Windows jako povinná závislost.** Dodává `git`, Git Bash pro Bash
  tool a hooky Claude Code [ověřeno: S14, S15] a OpenSSL DLL pro fulltext
  v GitNexus [ověřeno: S5].
- Balíčkový manažer: **winget**, s volitelným doplněním přes **Scoop** pro
  nástroje, které ve winget nejsou.
- Nová vrstva **platformního profilu** (`HostProfile`), která soustředí
  všechny rozdíly mezi OS do jednoho modulu. Režimy zůstanou bez `if windows`.
- Realizace ve fázích 0–8; fáze 7 (nativní qdrant) je součástí první verze. Fáze 0 ověří předpoklady na reálném Windows dřív, než
  se změní produkční kód.

---

## 2. Rozsah

### V rozsahu

- Windows 10 22H2+ a Windows 11, architektura x64.
- Nativní spuštění z PowerShellu, z CMD a z Git Bash.
- Instalace produktu (`--install`), kontrola a instalace závislostí
  (`--install-deps`), všechny režimy CLI a dashboard.
- Agenti Claude Code (nativní Windows) a Codex (nativní Windows).
- Dokumentace: README s oddělenou cestou pro Windows.
- Unit testy běžící na Windows a CI matrix.

### Mimo rozsah (první verze)

- Windows ARM64. Důvod je GitNexus (bod 7 shrnutí). Nástroj ale nesmí na ARM64
  spadnout; má vypsat jasnou diagnostiku.
- Linux jako oficiálně podporovaná platforma. Návrh profilu ho ale nesmí
  zablokovat. WSL 2 je v praxi Linux, viz strategie B.
- Konverze `defaults.env` na Windows. Na Windows bude podporovaný jen
  `defaults.toml` (kapitola 6.7).
- Kontejnery na Windows: Docker Desktop, Docker Engine ve WSL 2, Podman Desktop
  a Rancher Desktop. qdrant běží nativně (kapitola 6.12).
- Nativní `qdrant.exe` na macOS. macOS zůstává u kontejneru.

---

## 3. Současný stav

### 3.1 Co produkt dělá s OS

| Oblast | Současná implementace | Vazba na macOS/POSIX |
| --- | --- | --- |
| Launcher | Python soubor bez přípony, shebang `#!/usr/bin/env python3`, v instalaci `#!<sys.executable>` [kód: install.py:110, :312] | shebang, `chmod 0o755` |
| Instalace | `~/.local/bin`, `~/.local/lib/agent-code-intel` [kód: install.py:119, :123] | kontrola PATH přes `:` [kód: install.py:347–356], rada `export PATH` do `~/.zshrc` |
| Konfigurace | `${XDG_CONFIG_HOME:-$HOME/.config}/code-intel` [kód: cli.py:403–412] | `HOME` [kód: cli.py:386–387] |
| `defaults.env` | spouští reálný `bash` s harvesterem [kód: config.py:499–520] | `bash`, `env -0`, `/usr/bin/env` [kód: config.py:493–494] |
| Spouštění nástrojů | `subprocess.run(list(argv))` bez shellu [kód: integrations.py:46–63; commands.py:84] | resoluce `.cmd` na Windows |
| Pozadí | `subprocess.Popen(("ollama","serve"))` [kód: integrations.py:69–76] | bez odpojení od konzole |
| Qdrant HTTP | `curl … -o /dev/null` [kód: integrations.py:160–180] | `/dev/null` |
| Mazání kolekce | `curl -X DELETE` [kód: integrations.py:337–347] | závislost na `curl` |
| Kanonická cesta | `/bin/pwd -P` [kód: project.py:101–121] | `/bin/pwd` |
| Porovnání cest | `project.canon(mapped) == context.root` [kód: commands.py:705–706] | citlivost na velikost písmen a `\` vs `/` |
| Závislosti | `brew install` jen pro `Darwin` [kód: commands.py:282, :295] | Homebrew |
| Instalační rady | `curl … install.sh \| sh`, `brew upgrade node` [kód: commands.py:179–182, :2209] | POSIX shell |
| Claude hook | `python3 "${CLAUDE_PROJECT_DIR:-.}/.claude/helpers/code-context-hint.py"` [kód: hooks.py:15–17] | `${VAR:-default}` je syntaxe POSIX shellu |
| Codex hook | `/usr/bin/env python3 "$(git rev-parse --show-toplevel)/…"` [kód: hooks.py:18–20] | `/usr/bin/env`, `$(…)` |
| MCP registrace | `grepai mcp-serve …`, `gitnexus mcp` [kód: commands.py:991–1003] | `gitnexus` je na Windows `.cmd` |
| Dashboard: MCP servery | `ps -eo pid,etime,command`, `ps -o ppid=` [kód: code-intel-dash:174–235] | `ps` |
| Dashboard: logy | `~/Library/Logs/grepai/grepai-workspace-<ws>.log` [kód: code-intel-dash:426–429] | macOS cesta |
| Dashboard: launcher | hledá `agent-code-intel` s `os.access(X_OK)` a spouští ho přímo [kód: code-intel-dash:124–134, :245] | spuštění souboru se shebangem |
| Dashboard: npm | `~/.npm-global/…`, pak `npm root -g` [kód: code-intel-dash:187–191] | `npm` je na Windows `.cmd` |
| Testy | `test/unit.sh` a `test/run.sh` jsou Bash; `run.sh` používá `env -i` a `PATH=/usr/bin:/bin` | Bash, POSIX cesty |

### 3.2 Co je už přenositelné

Tyto části nevyžadují změnu, ale je nutné je potvrdit testem na Windows:

- Parsování `.code-intel`, registru (odděleno tabulátorem, takže `C:` v cestě
  nevadí) a TOML konfigurace [kód: project.py:185–205; config.py].
- Stav managed skills se porovnává po čtení v textovém režimu
  [kód: agent_skills.py:74–89]. Checkout s CRLF (Git `core.autocrlf=true`)
  tedy nezpůsobí falešný drift [odvozeno: Python v textovém režimu převádí
  `\r\n` na `\n`].
- Atomický zápis přes `tempfile.mkstemp` a `os.replace`
  [kód: agent_skills.py:123–128; hooks.py:232–237]. Na Windows ale `os.replace`
  selže, pokud cílový soubor drží otevřený jiný proces [neověřeno pro konkrétní
  soubory, viz riziko R6].
- `os.chmod` na Windows jen nastaví nebo zruší read-only. Nerozbije běh
  [neověřeno].
- `socket.create_connection` pro gRPC port [kód: integrations.py:183–193].
- Server dashboardu na `127.0.0.1` přes `http.server` a `webbrowser`
  [kód: code-intel-dash:2022].
- Názvy kontejneru a svazku qdrant na macOS. Na Windows se nepoužijí, protože
  qdrant běží nativně (kapitola 6.12).

---

## 4. Průzkum nástrojů na Windows

### 4.1 Přehled

„Windows x64“ znamená, že existuje oficiální nativní build.

| Nástroj | Úroveň | Windows x64 | Windows ARM64 | Doporučená instalace na Windows | Zdroj |
| --- | --- | --- | --- | --- | --- |
| Git | povinný | ano | — | `winget install --id Git.Git -e` | S14, S21 |
| Python 3.11+ | povinný | ano | — | Python install manager: `winget install --id Python.PythonInstallManager -e` | S18, S21 |
| Node.js 24.11+ | povinný | ano | — | `winget install --id OpenJS.NodeJS.LTS -e` (24.11.0+ je ve winget) | S21 |
| Kontejnery | na Windows nepotřebný | Docker Desktop, Podman Desktop, Rancher Desktop, Docker Engine ve WSL 2 | Docker Desktop je Early Access | — (zamítnuto, 4.2) | S12, S25, S29 |
| qdrant | povinný | nativní `qdrant-x86_64-pc-windows-msvc.zip` | není nativní build | **rozhodnuto:** nativní `qdrant.exe`, připnutá verze (6.12) | S1, S27 |
| Ollama | povinný | ano (`OllamaSetup.exe`, zip) | ano (`ollama-windows-arm64.zip`) | `winget install --id Ollama.Ollama -e` | S4, S13, S21 |
| grepai | povinný | ano (`windows_amd64.zip`) | zip existuje, `install.ps1` ho nepoužívá | `irm …/install.ps1 \| iex` | S3 |
| GitNexus | povinný | ano, s podmínkami | ne (LadybugDB) | `npm i -g gitnexus` + VC++ Redistributable | S5, S6 |
| `curl` | povinný dnes | [neověřeno] | — | navrženo odstranit (kapitola 6.3) | — |
| `rg` | doporučený | ano | ano | `winget install --id BurntSushi.ripgrep.MSVC -e` | S7, S21 |
| `ctags` (Universal) | doporučený | ano (6.1.0 a nightly) | — | `winget install --id UniversalCtags.Ctags -e` | S8, S21 |
| `ast-grep` | silně doporučený | ano | ano | `winget install --id ast-grep.ast-grep -e` | S9, S21 |
| `fd` | silně doporučený | ano | ano | `winget install --id sharkdp.fd -e` | S7, S21 |
| `rga` | silně doporučený | jen do 0.10.9 | ne | `scoop install rga` (Main bucket, 0.10.9) | S11 |
| `tokei` | silně doporučený | jen staré verze | ne | `scoop install tokei` (Main bucket, 12.1.2) | S10 |
| `scc` | silně doporučený | ano (`scc_Windows_x86_64.zip`) | ano | `scoop install scc` (Main bucket) | S10 |
| Claude Code | agent | ano | ano | `irm https://claude.ai/install.ps1 \| iex` nebo `winget install Anthropic.ClaudeCode` | S14 |
| Codex | agent | ano | [neověřeno] | `winget install --id OpenAI.Codex -e` | S16, S21 |

### 4.2 qdrant bez OrbStacku

OrbStack je jen pro macOS. Produkt ho přímo nevolá. Hledá první z `docker`,
`podman` a `nerdctl` na PATH [kód: integrations.py:231–237]. Na macOS to tak
zůstane. Na Windows se kontejner nepoužije.

**Požadavky na řešení pro Windows** (zadání 2026-09-17): použitelné pro firemní
vývoj bez licenčních omezení a nic se nesmí samo vypínat.

| Varianta | Licence pro firmu | Samo se vypíná? | Háček | Zdroj |
| --- | --- | --- | --- | --- |
| **Nativní `qdrant.exe`** — **zvoleno** | Apache-2.0 | ne, běžný proces | nový kód v produktu (6.12); instalace binárky z GitHub releases, protože ve winget ani ve Scoop Main není | S1, S27 |
| Docker Desktop | placený pro firmy s 250+ zaměstnanci **nebo** obratem nad 10 mil. USD | ne | licence | S12 |
| Docker Engine ve WSL 2 | zdarma | ano, nečinná distribuce se vypne po 15 s; služby systemd ji nedrží; lze vypnout `instanceIdleTimeout=-1`, ale po restartu Windows se musí nastartovat | Docker ho pro WSL nedokumentuje; sekce `[boot]` jen na Windows 11 | S24, S25, S26 |
| Podman Desktop | Apache-2.0 | u WSL varianty [neověřeno]; u Hyper-V [neověřeno] | vyžaduje administrátora; Hyper-V jen Windows Pro/Enterprise | S29 |
| Rancher Desktop | Apache-2.0 | [neověřeno] | na Windows pravděpodobně nad WSL [neověřeno] | S27 (licence z GitHub API) |
| PostgreSQL + pgvector místo qdrant | zdarma | ne, služba Windows | grepai workspace podporuje jen `postgres` a `qdrant`, GOB ne [ověřeno: S3]; pgvector se na Windows kompiluje přes Visual Studio jako administrátor [ověřeno: S30] | S3, S30 |

Qdrant Cloud ani vzdálený server nepřipadají v úvahu. Porušily by princip, že
stack běží jen lokálně [README: „Runs 100% locally“].

**Důkazy pro nativní qdrant na Windows** [ověřeno: S27]:

- licence repozitáře `qdrant/qdrant` je Apache-2.0,
- release workflow má job `build-windows-binaries` a release v1.19.1 obsahuje
  `qdrant-x86_64-pc-windows-msvc.zip`; GitHub API uvádí jeho SHA-256 digest,
- Rust testy běží v matrixu `ubuntu-latest`, `windows-latest`, `macos-latest`,
- kontrola souborového systému vrací pro NTFS `FsCheckResult::Good`.

**Co chybí:** Instalační dokumentace qdrant popisuje Docker, Kubernetes a build
ze zdrojů. Instalaci z hotové binárky ani produkční podporu Windows výslovně
nepopisuje [ověřeno: S2]. Riziko R2.

### 4.3 Ollama

- Nativní Windows 10 22H2+, edice Home i Pro. `OllamaSetup.exe` se instaluje do
  uživatelského účtu **bez práv administrátora** [ověřeno: S4].
- Po instalaci „Ollama will run in the background“ jako aplikace v oznamovací
  oblasti. API je na `http://localhost:11434` [ověřeno: S4].
- Pro běh jako služba existuje samostatný zip a `ollama serve` s nástrojem
  typu NSSM [ověřeno: S4].
- Balíček winget `Ollama.Ollama` existuje [ověřeno: S21].

**Dopad:** Ekvivalent `brew services start ollama` není potřeba, protože se
tray aplikace spouští sama. Bootstrap produktu, který spouští `ollama serve`
[kód: integrations.py:293–299], musí na Windows proces odpojit od konzole.
Jinak zavření terminálu ukončí server [odvozeno: S22 — `start_new_session` je
jen POSIX; na Windows jsou potřeba `creationflags`]. Lepší je na Windows
nejdřív navrhnout spuštění tray aplikace [neověřeno: přesný název a cesta
spustitelného souboru tray aplikace].

### 4.4 Python

- Python install manager je od 3.14 doporučený způsob instalace. Klasický
  instalátor je zastaralý a pro Python 3.16+ nevyjde [ověřeno: S18].
- Po instalaci jsou k dispozici `python`, `py` a `pymanager`. Příkaz `python3`
  existuje, ale dokumentace ho „nedoporučuje k širokému použití“
  [ověřeno: S18].
- Windows může příkaz `python` přesměrovat na Microsoft Store přes „App
  execution aliases“ [ověřeno: S18].

**Dopad:**

- README pro Windows musí používat `python` (nebo `py`), ne `python3`.
- Hooky nesmí spoléhat na `python3` (kapitola 6.5).
- Launcher na Windows musí odkazovat na absolutní cestu `sys.executable` z
  instalace, stejně jako dnes na macOS [kód: install.py:312].
- Runtime gate pro Python < 3.11 zůstává beze změny [kód: agent-code-intel].

### 4.5 Node.js a GitNexus

- `gitnexus` 1.6.12 deklaruje `engines.node: ^22.18.0 || >=24.11.0` a `bin`
  `dist/cli/index.js` [ověřeno: S6].
- `tree-sitter` 0.21.1 má prebuild `win32-x64`. Vendorované gramatiky mají
  prebuildy pro `win32-x64` i `win32-arm64`. Bez prebuildu se kompilují ze
  zdrojů, což vyžaduje C++ toolchain [ověřeno: S6].
- `@ladybugdb/core` 0.18.3 (grafová DB) má volitelné nativní balíčky jen pro
  `darwin-arm64`, `darwin-x64`, `linux-arm64`, `linux-x64` a **`win32-x64`**
  [ověřeno: S6]. **Na Windows ARM64 tedy chybí** [odvozeno].
- Fulltext v GitNexus potřebuje na Windows **Microsoft Visual C++ 2015–2022
  Redistributable (x64)** a **OpenSSL 3 DLL** na PATH. Git for Windows DLL
  dodává v `C:\Program Files\Git\mingw64\bin`. Bez nich `analyze` projde, ale
  hledání podle klíčových slov vrací prázdné výsledky. Oprava je
  `gitnexus analyze --repair-fts` [ověřeno: S5].
- GitNexus README pro Windows registruje MCP přes `cmd /c`:
  `claude mcp add gitnexus -- cmd /c npx -y gitnexus@latest mcp` [ověřeno: S5].
- npm na Windows dává globální spustitelné soubory přímo do prefixu
  `%AppData%\npm` [ověřeno: S23]. Jsou to `.cmd` a `.bat` shimy, které nejdou
  spustit bez shellu [ověřeno: S15].

**Dopad:**

1. Preflight na Windows musí kontrolovat VC++ Redistributable a dostupnost
   OpenSSL DLL. Chybějící OpenSSL = `warn` s odkazem na `--repair-fts`.
2. Volání `gitnexus` musí jít přes resoluci `.cmd` (kapitola 6.2).
3. MCP registrace `gitnexus` na Windows musí mít tvar `cmd /c gitnexus mcp`
   (kapitola 6.6).
4. Rada při chybě `brew upgrade node && npm i -g gitnexus`
   [kód: commands.py:2209] musí být platformní.
5. Dashboard hledá balíček v `~/.npm-global/lib/node_modules/gitnexus`
   [kód: code-intel-dash:187]. Na Windows je výchozí
   `%AppData%\npm\node_modules\gitnexus` [odvozeno: S23].

### 4.6 grepai

- Release obsahuje `grepai_<ver>_windows_amd64.zip` a
  `grepai_<ver>_windows_arm64.zip` [ověřeno: S3].
- Oficiální `install.ps1` instaluje do `%LOCALAPPDATA%\Programs\grepai` a
  přidá adresář do uživatelského PATH. **Vybírá natvrdo `windows_amd64`**
  [ověřeno: S3].
- Démon má implementaci pro Windows (`daemon/daemon_windows.go`, `LockFileEx`,
  `OpenProcess`) [ověřeno: S3].
- Logy démona na Windows: `%LOCALAPPDATA%\grepai\logs`. Soubory mají předponu
  `grepai-workspace-` [ověřeno: S3].
- grepai má dokončování pro PowerShell [ověřeno: S3].

**Dopad:** Instalační rada v `_INSTALL_DEPS_COMMANDS` [kód: commands.py:179–182]
musí mít variantu pro PowerShell:
`irm https://raw.githubusercontent.com/yoanbernabeu/grepai/main/install.ps1 | iex`.
Dashboard musí číst logy z platformní cesty.

### 4.7 Nástroje code-context

| Nástroj | Nález | Zdroj |
| --- | --- | --- |
| `rg` | winget `BurntSushi.ripgrep.MSVC` až 15.2.0; release zip pro x64, x86 a ARM64 | S7, S21 |
| `ctags` | winget `UniversalCtags.Ctags` (6.1.0, Nightly); Scoop Extras `universal-ctags`; `ctags-win32` release 6.1.0 | S8, S21 |
| `ast-grep` | winget `ast-grep.ast-grep`; release zip pro x64, x86 a ARM64; Scoop Main | S9, S21 |
| `fd` | winget `sharkdp.fd` až 10.5.0 | S7, S21 |
| `rga` | poslední release v0.10.10 **nemá** Windows asset; Scoop Main `rga` 0.10.9 s Windows zip, závisí na `ffmpeg`, `pandoc`, `poppler`, `ripgrep` | S11 |
| `tokei` | releasy v13.0.0, v14.0.0 a v15.0.0 **nemají** Windows asset; Scoop Main `tokei` 12.1.2 | S10 |
| `scc` | release v4.1.0 má `scc_Windows_x86_64.zip` a `scc_Windows_arm64.zip`; Scoop Main `scc`; ve winget pod `boyter.scc` ani `benboyter.scc` nenalezen | S10, S21 |

**Poznámka k `ctags`:** Kontrola „Universal Ctags“ podle banneru `--version`
[kód: integrations.py:115–132] platí i na Windows. Na Windows není BSD ctags,
takže třetí stav („present but BSD“) tam prakticky nenastane [odvozeno].

**Poznámka k textu hintu a skills:** Hint doporučuje
`TMPDIR=. ctags … | rg …` [kód: assets/code-context-hint.py]. Předpona
`TMPDIR=.` je syntaxe POSIX shellu. V Git Bash funguje, v PowerShellu ne. Zda
ctags na Windows čte `TMPDIR`, nebo `TMP`/`TEMP`, je [neověřeno].

### 4.8 Agenti

**Claude Code** [ověřeno: S14, S15]:

- Běží nativně na Windows 10 1809+ a Windows Server 2019+, x64 i ARM64.
- Nativní instalace dává `%USERPROFILE%\.local\bin\claude.exe`. Je to stejný
  adresář `.local\bin`, který používá instalátor `agent-code-intel`.
- Git for Windows je volitelný. S ním Claude Code používá Git Bash pro Bash
  tool. Bez něj používá PowerShell tool. Cestu k Git Bash lze nastavit přes
  `CLAUDE_CODE_GIT_BASH_PATH`.
- Command hooky ve „shell form“ běží přes `sh -c` na macOS, přes **Git Bash**
  na Windows a přes **PowerShell**, když Git Bash chybí. Pole `shell` volí
  `bash` nebo `powershell`.
- „Exec form“ (`command` + `args`) spouští program přímo, bez shellu.
  Zástupné proměnné jako `${CLAUDE_PROJECT_DIR}` se dosadí do `args`.
  **Na Windows musí `command` být skutečný `.exe`**, ne `.cmd` shim.
  Dokumentace doporučuje vzor `node` + cesta ke skriptu, který „works on every
  platform“.

**Codex** [ověřeno: S16, S17]:

- Běží nativně v PowerShellu s Windows sandboxem. WSL je doporučené, jen když
  je potřeba linuxový toolchain.
- Hook má volitelné pole `commandWindows` (v TOML `command_windows`) jako
  přepis příkazu pro Windows.
- Příkaz hooku běží v `cwd` session. Dokumentace doporučuje resolvovat cestu od
  kořene gitu.
- Na Windows Codex použije `command_windows`, a když chybí, `command`
  [ověřeno: S31, `codex-rs/hooks/src/engine/discovery.rs:513–517`].
- Příkaz spouští shell session. Když ho Codex nemá, použije `%COMSPEC%` s `/C`,
  výchozí `cmd.exe` [ověřeno: S31, `codex-rs/hooks/src/engine/command_runner.rs:435–437`,
  `codex-rs/core/src/session/mod.rs:4989–4997`]. Zda je shell session na
  Windows PowerShell, je [neověřeno]. **Příkaz hooku proto musí fungovat
  v PowerShellu i v `cmd.exe`.**
- Zda je nativní Windows podpora Codexu stále označená jako experimentální, je
  [neověřeno]; oficiální stránka to neuvádí.

---

## 5. Analýza kódu: nálezy

Závažnost:

- **B (blokující):** režim na Windows nefunguje.
- **F (funkční):** režim běží, ale dává špatný výsledek nebo radu.
- **K (kosmetické):** text nebo dokumentace.

| # | Místo | Problém na Windows | Závažnost | Návrh (kapitola) |
| --- | --- | --- | --- | --- |
| N1 | install.py:290–320 | launcher bez přípony se shebangem nejde spustit | B | `.cmd` shim (6.1) |
| N2 | install.py:347–356 | PATH se dělí `:`; rada `export PATH` do `~/.zshrc` | F | `os.pathsep`, rada pro PowerShell (6.1) |
| N3 | integrations.py:46–63; commands.py:84–97 | `.cmd` shimy (`gitnexus`, `npm`, případně `codex`) nejdou spustit bez shellu; výsledek 127 | B | resoluce spustitelného souboru (6.2) |
| N4 | integrations.py:111–113 | `have()` přes `shutil.which` najde `.cmd`, ale `_run` ho nespustí; preflight lže | F | stejná resoluce pro `have` i `_run` (6.2) |
| N5 | integrations.py:160–180 | `curl -o /dev/null` | B | `urllib.request` (6.3) |
| N6 | integrations.py:337–347 | `curl -X DELETE` | F | `urllib.request` (6.3) |
| N7 | integrations.py:69–76, :293–299 | `ollama serve` není odpojený od konzole | F | `creationflags` (6.2) |
| N8 | project.py:101–121 | `/bin/pwd -P` neexistuje; fallback `pwd` není `.exe`, takže vrátí vstup beze změny | F | `os.path.realpath` + `normcase` (6.8) |
| N9 | commands.py:705–706, :944, :1209, :1665, :1926 | `canon(mapped) == root` porovnává řetězce; na Windows rozdíl ve velikosti písmen nebo `\`/`/` způsobí falešný `CONFLICT` | F | `same_path()` (6.8) |
| N10 | commands.py:179–182, :252–310 | instalace jen přes Homebrew a jen pro `Darwin`; rada pro grepai je `curl \| sh` | B pro `--install-deps` | profil + winget (6.4) |
| N11 | commands.py:2209 | rada `brew upgrade node` | K | profil (6.4) |
| N12 | hooks.py:15–20 | Claude hook používá `${VAR:-.}` a `python3`; Codex hook `/usr/bin/env` a `$(…)` | B pro hook | exec form a `commandWindows` (6.5) |
| N13 | commands.py:991–1003 | MCP `gitnexus mcp` na Windows nespustí `.cmd` | B pro MCP GitNexus | `cmd /c gitnexus mcp` (6.6) |
| N14 | config.py:499–520 | `defaults.env` vyžaduje `bash`; s Git Bash by teoreticky běžel, ale harvester volá `env -0` a `/usr/bin/env` | F | na Windows jen TOML (6.7) |
| N15 | cli.py:386–387 | `HOME` na Windows obvykle není nastavený; fallback `expanduser("~")` funguje. V Git Bash `HOME` nastavený je, takže se výsledek může lišit podle shellu | F | jednotná resoluce domova (6.7) |
| N16 | code-intel-dash:174–235 | `ps -eo`, `ps -o ppid=` | F | PowerShell/CIM (6.9) |
| N17 | code-intel-dash:426–429 | cesta `~/Library/Logs/grepai` | F | profil (6.9) |
| N18 | code-intel-dash:124–134, :245 | hledá soubor bez přípony a spouští ho přímo | B pro dashboard | `sys.executable` + cesta k launcheru (6.9) |
| N19 | code-intel-dash:187–191 | `~/.npm-global`, `npm root -g` (`.cmd`) | F | profil + resoluce (6.9) |
| N20 | install.py:379 | `os.access(dst, os.X_OK)` na Windows nic neříká o spustitelnosti | K | kontrola jen existence (6.1) |
| N21 | test/unit.sh, test/run.sh | Bash a POSIX `PATH` | F pro vývoj | `python -m unittest` a CI matrix (6.10) |
| N22 | assets/code-context-hint.py, SKILL.md | příkazy v syntaxi POSIX shellu (`TMPDIR=.`, `\|`, `wc -l`) | F pro agenta v PowerShellu | Git Bash jako povinnost; platformní text hintu (6.5) |
| N23 | project.py:523–531 | hash legacy `refresh-intel.sh` se počítá z bajtů; checkout s CRLF dá jiný hash | K | normalizovat konce řádků před hashem (6.8) |
| N24 | README.md | celé je pro macOS; badge `platform-macOS` | K | oddělená cesta pro Windows (6.11) |

---

## 6. Návrh řešení

### 6.0 Princip: platformní profil jako jediný seam

Dnes je rozdíl mezi OS jen v `run_install_deps` přes parametr
`system=platform.system()` [kód: commands.py:252–258]. Návrh tento vzor
zobecňuje.

Nový modul `agent_code_intel/hostos.py` (název se liší od stdlib `platform`):

```python
@dataclasses.dataclass(frozen=True)
class HostProfile:
    name: str                      # "darwin" | "windows" | "linux"
    arch: str                      # "x64" | "arm64"
    package_manager: str           # "brew" | "winget" | ""
    # Instalace nástroje: jméno -> (manažer, id) nebo ruční příkaz
    install_specs: Mapping[str, InstallSpec]
    grepai_log_dir: str
    npm_global_root_hint: str
    path_advice: tuple[str, ...]   # řádky rady pro PATH
    node_upgrade_hint: str
    def resolve_executable(self, name: str, path: str) -> tuple[str, ...]: ...
    def detached_spawn_kwargs(self) -> dict: ...
    def hook_registration(self, agent: str) -> dict: ...
    def mcp_command(self, tool: str, args: tuple[str, ...]) -> tuple[str, ...]: ...

def detect(environ: Mapping[str, str]) -> HostProfile: ...
```

Pravidla:

1. `detect()` se volá jednou v `cli.main` a profil se předá dolů, stejně jako
   dnes `env`, `cwd` a streamy [kód: agent-code-intel; cli.py].
2. Režimy (`commands.py`) nesmí obsahovat `if os.name == "nt"`. Pouze se ptají
   profilu.
3. Testy předají explicitní profil (`darwin`, `windows`). Windows chování lze
   tak unit-testovat i na macOS. Testy, které sahají na skutečný FS nebo
   procesy, poběží na Windows v CI.
4. Neznámé OS nebo Windows ARM64: profil vrátí stav „nepodporováno“ a preflight
   vypíše jasnou chybu ve formátu `[ERROR: …]`, žádný traceback.

### 6.1 Instalátor produktu (`--install`) na Windows

Rozložení zůstává stejné, aby README, dashboard a Claude Code sdílely adresář:

```
%USERPROFILE%\.local\bin\agent-code-intel.cmd
%USERPROFILE%\.local\bin\code-intel-dash.cmd
%USERPROFILE%\.local\lib\agent-code-intel\agent_code_intel\...
%USERPROFILE%\.local\lib\agent-code-intel\launcher.py
%USERPROFILE%\.local\lib\agent-code-intel\code-intel-dash
```

Nativní instalace Claude Code používá `%USERPROFILE%\.local\bin\claude.exe`
[ověřeno: S14]. U uživatelů Claude Code proto adresář na PATH pravděpodobně už
je [odvozeno].

**Shim `.cmd`:**

```bat
@echo off
"C:\Users\me\AppData\Local\Python\...\python.exe" "%~dp0..\lib\agent-code-intel\launcher.py" %*
```

- Absolutní cesta k `sys.executable` odpovídá dnešnímu chování na macOS
  (`#!<sys.executable>`) [kód: install.py:312].
- Launcher se na Windows přesune do `lib` jako `launcher.py`. Na macOS se nic
  nemění.
- **Riziko:** CMD parsuje `%*`. Argumenty se znaky `&`, `|`, `^` nebo `%` se
  mohou rozbít [ověřeno obecně: S22, poznámka o batch souborech]. CLI přijímá
  jen flagy, cesty a jméno workspace, takže riziko je nízké. Je ale nutné ho
  zdokumentovat.
- **Alternativa:** `pyproject.toml` s `console_scripts` a instalace přes
  `pipx` nebo `uv tool install`, které na Windows vytvoří skutečný `.exe`
  [neověřeno pro konkrétní verze pipx/uv]. Mění to ale distribuční model
  („checkout + `--install`“). **Rozhodnuto (Q4):** `.cmd` shim.

**Rozhodnuto:** umístění `%USERPROFILE%\.local\bin` a `%USERPROFILE%\.local\lib`
(Q11), konfigurace `%USERPROFILE%\.config\code-intel` (Q7).

**PATH:**

- Kontrola přes `os.pathsep` a porovnání s `os.path.normcase` (N2).
- Rada na Windows (PowerShell, bez administrátora):

  ```powershell
  [Environment]::SetEnvironmentVariable("Path", "$env:USERPROFILE\.local\bin;" + [Environment]::GetEnvironmentVariable("Path", "User"), "User")
  ```

- Instalátor PATH sám **nemění**, stejně jako na macOS jen radí. Zachová se
  tím dnešní chování.

**Oprávnění Claude:** Instalátor přidává `Bash(agent-code-intel --refresh)`
do `~/.claude/settings.json`. S Git for Windows je PowerShell tool dostupný
vedle Bash toolu a pro účty claude.ai a Console je zapnutý ve výchozím stavu
[ověřeno: S14]. Pravidla pro PowerShell mají tvar `PowerShell(<vzor>)`
[ověřeno: S32].

**Rozhodnuto (Q6):** instalátor na Windows zapíše obě pravidla:

```json
"allow": [
  "Bash(agent-code-intel --refresh)",
  "PowerShell(agent-code-intel --refresh)"
]
```

- macOS se nemění, zapisuje jen pravidlo pro Bash.
- `--no-perms` přeskočí obě pravidla.
- Zda pravidlo `PowerShell(agent-code-intel --refresh)` pokryje volání shimu
  `agent-code-intel.cmd`, je [neověřeno]. Ověří fáze 0.

### 6.2 Spouštění externích nástrojů

Jedna funkce v profilu, kterou používají `Stack.have`, `Stack._run`,
`Stack._spawn`, `CommandRunner.run` i dashboard:

```text
resolve_executable(name, PATH):
  full = shutil.which(name, path=PATH)
  if full is None:            -> None (výsledek 127, jako dnes)
  if windows and full má příponu .cmd/.bat:
      if name == "gitnexus": -> (node.exe, <npm root>\gitnexus\dist\cli\index.js)
      else:                  -> (%COMSPEC%, "/d", "/s", "/c", full)
  else:                       -> (full,)
```

Zdůvodnění:

- `CreateProcess` bez přípony doplňuje jen `.exe` a batch soubory spouští přes
  `cmd.exe /c` [ověřeno: S20].
- `subprocess` na Windows při `shell=False` nepoužije `PATH` z předaného `env`
  [ověřeno: S22]. Produkt ale předává dětský `env` s vlastním PATH
  [kód: integrations.py:104–105]. **Absolutní cesta z `shutil.which` je proto
  nutná, ne volitelná.**
- Pro `gitnexus` se doporučuje `node` + skript. Vyhne se parsování argumentů
  přes CMD a odpovídá vzoru z dokumentace Claude Code [ověřeno: S15]. Cesta
  skriptu je z `bin` v package.json [ověřeno: S6].
- Python varuje, že batch soubory mohou parsovat argumenty podle pravidel
  shellu bez escapování [ověřeno: S22]. Přes `cmd /c` smí jít jen argumenty,
  které produkt sám generuje (flagy, slug workspace). Uživatelský text, např.
  dotaz z karty Search v dashboardu, jde jen do `grepai.exe`, tedy ne přes CMD.

**Procesy na pozadí:** `detached_spawn_kwargs()` vrátí na Windows
`creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` [ověřeno: S22] a na
POSIX dnešní chování.

### 6.3 Odstranění `curl`

`curl` slouží jen pro HTTP health a mazání kolekce [kód: integrations.py:160–180,
:337–347]. Dashboard už používá `urllib.request` [kód: code-intel-dash:97–110].

Návrh: přepsat obě volání na `urllib.request` se stejnými timeouty
(`_PROBE_CONNECT_TIMEOUT_S`, `_PROBE_TOTAL_TIMEOUT_S`). Výhody:

- odpadne otázka, zda je `curl.exe` na Windows [neověřeno],
- odpadne `/dev/null`,
- `curl` zmizí ze seznamu povinných závislostí na všech platformách.

**Pozor:** `curl` je v README v tabulce povinných závislostí. Změna je
viditelná pro uživatele a patří do CHANGELOG.

### 6.4 Závislosti (`--install-deps`) na Windows

**Detekce správce balíčků:** `winget` na PATH. Scoop jako volitelný doplněk,
jen když `scoop` na PATH je.

**Mapování** (id z S21 a S10/S11):

| Nástroj | winget id | Scoop | Ruční příkaz |
| --- | --- | --- | --- |
| rg | `BurntSushi.ripgrep.MSVC` | `ripgrep` [neověřeno] | — |
| ctags | `UniversalCtags.Ctags` | `universal-ctags` (Extras) | — |
| ast-grep | `ast-grep.ast-grep` | `ast-grep` | `npm i -g @ast-grep/cli` [neověřeno] |
| fd | `sharkdp.fd` | `fd` [neověřeno] | — |
| rga | — | `rga` | — |
| tokei | — | `tokei` (12.1.2) | `cargo install tokei` [neověřeno] |
| scc | [neověřeno] | `scc` | zip z GitHub releases |
| grepai | — | — | `irm https://raw.githubusercontent.com/yoanbernabeu/grepai/main/install.ps1 \| iex` |
| gitnexus | — | — | `npm i -g gitnexus` |

**Chování** (zrcadlí dnešní macOS logiku [kód: commands.py:252–310]):

1. Vypsat stav všech devíti nástrojů.
2. Vypsat příkazy `winget install --id <id> -e` pro chybějící.
3. S TTY a bez `--no-install-deps` nabídnout `[y/N]` a spustit winget po
   jednom balíčku. winget nemá jeden příkaz pro více id [neověřeno].
4. Bez TTY jen vypsat příkazy a nic neinstalovat.
5. Návratové kódy beze změny.

**Rozšíření jen pro Windows:** Preflight `--apply` přidá kontroly:

- VC++ Redistributable x64 (winget `Microsoft.VCRedist.2015+.x64` [ověřeno:
  S21]). Detekce přes registr je [neověřeno].
- OpenSSL DLL `libssl-3-x64.dll` a `libcrypto-3-x64.dll` na PATH pro fulltext
  GitNexus [ověřeno: S5]. Úroveň `warn`, ne `MISSING`.
- Git Bash dostupný (kvůli hookům a Bash toolu Claude Code).
- Kontroly nativního qdrant z [kapitoly 6.12](#612-qdrant-na-windows-nativní-qdrantexe).

**Co se neinstaluje automaticky:** Python, Node.js, Git a Ollama. README je
uvede jako ruční kroky s příkazy winget. Na macOS je `--install-deps` také
neinstaluje [kód: commands.py:168–182]. `qdrant.exe` je výjimka: stáhne ho
`--install-deps` (rozhodnutí Q15, kapitola 6.12).

### 6.5 Hooky SessionStart

Soubor `.claude/settings.json` i `.codex/hooks.json` je verzovaný
[README: „The routing skill is deliberately versionable“]. **Jedna registrace
proto musí fungovat pro Mac i Windows v jednom týmu.**

**Claude Code — návrh:** přejít na exec form, bez shellu:

```json
{
  "type": "command",
  "command": "node",
  "args": ["${CLAUDE_PROJECT_DIR}/.claude/helpers/code-context-hint.mjs"],
  "timeout": 5000
}
```

- `node.exe` je skutečný binární soubor. Vzor `node` + skript podle dokumentace
  „works on every platform“ [ověřeno: S15].
- Node.js je už povinná závislost (GitNexus).
- `${CLAUDE_PROJECT_DIR}` se v exec form dosadí do `args` bez quotingu
  [ověřeno: S15].
- **Cena:** hint se přepíše z Pythonu do JavaScriptu. Mění se spravovaný artefakt
  a migrace existujících projektů (`--apply` musí rozpoznat starou registraci
  jako vlastní a nahradit ji).

**Alternativa bez přepisu:** exec form s `"command": "python"`. Na macOS ale
`python` často neexistuje, existuje jen `python3` (Homebrew) [neověřeno pro
všechny instalace]. Na Windows je naopak `python3` „nedoporučený“
[ověřeno: S18]. Jedna hodnota tedy nepokryje obě platformy.
**Rozhodnuto: Node.**

**Codex — návrh:**

```json
{
  "type": "command",
  "command": "node \"$(git rev-parse --show-toplevel)/.claude/helpers/code-context-hint.mjs\"",
  "commandWindows": "node .claude/helpers/code-context-hint.mjs",
  "timeout": 5
}
```

- `commandWindows` existuje [ověřeno: S17] a Codex ho na Windows použije místo
  `command` [ověřeno: S31].
- Příkaz běží v shellu session, nebo v `cmd.exe` [ověřeno: S31].
  `$(git rev-parse …)` funguje v PowerShellu, v `cmd.exe` ne [odvozeno].
- **Rozhodnuto (Q3):** `commandWindows` s relativní cestou
  `node .claude/helpers/code-context-hint.mjs`. Neobsahuje shellovou syntaxi,
  takže funguje v PowerShellu i v `cmd.exe` [odvozeno].
- **Omezení:** Příkaz běží v `cwd` session [ověřeno: S17]. Když uživatel spustí
  Codex z podadresáře, `node` skript nenajde a hint v té session chybí.
  Dokumentace Codexu na tento případ upozorňuje [ověřeno: S17]. README pro
  Windows proto doporučí spouštět Codex z kořene repozitáře.
- Zvažované a zamítnuté varianty: stejný příkaz bez `commandWindows` (selže
  v `cmd.exe`), nový režim `agent-code-intel --hook-hint` (hook by závisel na
  instalaci nástroje a změnil by repo-lokální návrh), `exit 0` (Codex na
  Windows by hint neměl vůbec).

**Obsah hintu:** Skript zná OS (`process.platform`). Na Windows může text
říkat, že příkazy platí pro Git Bash, nebo nabídnout variantu pro PowerShell.
**Rozhodnuto (Q5):** Git for Windows je povinný a hint i skills zůstávají jen
v Bash syntaxi. Pro Claude Code pak Bash tool běží v Git Bash [ověřeno: S14] a
text zůstane stejný. Codex běží v PowerShellu [ověřeno: S16], takže Bash
příkazy ze skills tam nemusí fungovat. PowerShell varianty budou samostatné
issue po první verzi.

### 6.6 Registrace MCP

| Server | macOS (dnes) | Windows (návrh) | Zdůvodnění |
| --- | --- | --- | --- |
| grepai (Claude, projekt, `.mcp.json`) | `grepai mcp-serve --workspace <ws>` | beze změny | `grepai.exe` je skutečný binární soubor [ověřeno: S3] |
| grepai (Codex) | totéž | beze změny | totéž |
| gitnexus (Claude, uživatel) | `gitnexus mcp` | `cmd /c gitnexus mcp` | vzor z README GitNexus [ověřeno: S5] |
| gitnexus (Codex) | `gitnexus mcp` | `cmd /c gitnexus mcp` | [odvozeno]; ověřit ve fázi 0 |

- `.mcp.json` je verzovaný, ale obsahuje jen grepai. Registrace gitnexus je
  v uživatelském scope, takže se týmově nesdílí [kód: commands.py:999–1003].
  Rozdílné tvary na Mac a Windows proto nevadí.
- Stav `--status` musí považovat obě varianty za platné. Jinak projekt
  otevřený na obou OS ukáže falešný drift.
- Příkazy `claude mcp …` a `codex mcp …` se spouštějí přes resoluci z 6.2
  (`codex` z npm je `.cmd` [odvozeno]).

### 6.7 Konfigurace a domovský adresář

- **Adresář konfigurace:** zachovat `%USERPROFILE%\.config\code-intel`
  (respektovat `XDG_CONFIG_HOME`). Je to v souladu s `~/.claude` a README
  zůstane jednotné. **Rozhodnuto (Q7).**
- **Domov:** na Windows `USERPROFILE`, s fallbackem na `expanduser("~")`.
  Proměnnou `HOME` ignorovat, protože Git Bash ji nastavuje jinak a výsledek by
  závisel na shellu (N15). Na macOS se nic nemění.
- **`defaults.env` na Windows (rozhodnuto):** nepodporovat. Když existuje, skončit chybou
  `[ERROR: defaults.env is not supported on Windows; convert it to defaults.toml]`.
  Zdůvodnění: harvester je Bash skript s `env -0` a `/usr/bin/env`
  [kód: config.py:427–496], Windows nemá historické uživatele s ENV, a TOML je
  už plnohodnotná náhrada [README, sekce Configuration].

### 6.8 Cesty

Nová funkce `project.same_path(a, b)`:

```text
same_path(a, b) = normcase(realpath(a)) == normcase(realpath(b))
```

- Na Windows `os.path.normcase` převede na malá písmena a `/` na `\`
  [neověřeno: chování pro UNC cesty a pro disky mapované přes `subst`].
- `canon()` na Windows: `os.path.realpath`. Zda vrací skutečnou velikost
  písmen z disku, je [neověřeno]. Pro porovnání to nevadí díky `normcase`.
  Pro zobrazení je to kosmetické.
- Nahradit všech pět porovnání `canon(mapped) == root` (N9).
- Registr: `registry_add` a `registry_delete` porovnávají cestu řetězcem
  [kód: project.py:408–435]. Na Windows porovnávat přes `same_path`.
- Hash legacy `refresh-intel.sh` počítat po normalizaci `\r\n` na `\n` (N23).
- **Rozhodnuto (Q8):** `.gitattributes` do cílových projektů nezapisovat.
  Konce řádků řeší normalizace v kódu (N23) a textové porovnání skills.

### 6.9 Dashboard

| Funkce | macOS (dnes) | Windows (návrh) |
| --- | --- | --- |
| nalezení launcheru | soubor `agent-code-intel` s `X_OK` | `agent-code-intel.cmd` na PATH, nebo `launcher.py` v `lib`; spouštět jako `(sys.executable, launcher.py, …)` |
| procesy `gitnexus mcp` | `ps -eo pid,etime,command` | `powershell -NoProfile -Command "Get-CimInstance Win32_Process \| Select-Object ProcessId,ParentProcessId,CreationDate,CommandLine \| ConvertTo-Json"` [neověřeno: formát `CreationDate` v JSON] |
| vlastník procesu | `ps -o command= -p <ppid>` | ze stejného CIM výpisu podle `ParentProcessId` |
| logy watcheru | `~/Library/Logs/grepai` | `%LOCALAPPDATA%\grepai\logs` [ověřeno: S3] |
| balíček gitnexus | `~/.npm-global/…`, `npm root -g` | `%AppData%\npm\node_modules\gitnexus` [odvozeno: S23], pak `npm root -g` přes resoluci 6.2 |
| rada pro Node | `brew upgrade node` | `winget upgrade --id OpenJS.NodeJS.LTS -e` |

- Logika zůstává v dashboardu. Platformní data (cesta k logům, rada) čte
  z `hostos`, který už dashboard importuje přes `load_pkg`
  [kód: code-intel-dash:601–638].
- `stdlib` pravidlo zůstává: žádný `psutil`.
- Dashboard na Windows spustitelný přes `code-intel-dash.cmd`.

### 6.10 Testy a CI

- **Unit testy:** přidat přenositelný vstup
  `python -m unittest discover -s test/unit -t test/unit`. `test/unit.sh` zůstává
  pro macOS.
- **Profil jako parametr:** testy seamů pro Windows (resoluce `.cmd`, tvar
  hooků, tvar MCP, PATH rada, mapování winget) poběží na obou OS s explicitním
  profilem.
- **Testy jen pro Windows** (`@unittest.skipUnless(os.name == "nt")`):
  skutečný `.cmd` shim z instalátoru, `os.replace` na otevřený soubor,
  `realpath` a `normcase`.
- **`test/launcher`:** test porovnává zdrojový launcher se šablonou
  [kód: install.py:1–10 docstring]. Přidat totéž pro `.cmd` šablonu.
- **Černá skříňka `test/run.sh`:** zůstává Bash a jen pro macOS. Na Windows ho
  nepřepisovat v první verzi. Pokrytí zajistí unit testy a ruční akceptace
  (fáze 8).
- **CI:** repozitář dnes nemá `.github/workflows` [kód: git ls-files]. Návrh:
  GitHub Actions matrix `macos-latest` a `windows-latest`, Python 3.11 a
  nejnovější, jen unit testy. Integrace se stackem (Docker, Ollama) v CI
  nepoběží.

### 6.11 Dokumentace

- README: rozdělit na společný úvod a dvě instalační cesty, „macOS“ a
  „Windows“. Tabulky flagů a exit kódů zůstanou společné.
- Windows cesta: PowerShell příkazy, winget, nativní qdrant, Git for Windows,
  Python install manager, `python` místo `python3`.
- Troubleshooting pro Windows: App execution aliases pro Python [ověřeno: S18],
  fulltext GitNexus a `--repair-fts` [ověřeno: S5], qdrant neběží po restartu,
  obsazený port 6333/6334, upgrade qdrant o více minor verzí [ověřeno: S28].
- Badge `platform-macOS` změnit na `macOS | Windows`.
- CHANGELOG: každá fáze s viditelnou změnou dostane záznam podle
  `docs/agents/changelog.md`.

### 6.12 qdrant na Windows: nativní `qdrant.exe`

**Rozhodnutí (Q1):** na Windows běží qdrant jako nativní proces uživatele.
macOS zůstává u kontejneru.

#### Architektura

```
Windows (uživatel, bez administrátora)
─────────────────────────────────────
agent-code-intel ──spawn──> qdrant.exe  (127.0.0.1:6333 HTTP, 127.0.0.1:6334 gRPC)
grepai.exe ─────────gRPC──>     │
dashboard ──────────HTTP──>     └─ %LOCALAPPDATA%\code-intel\qdrant\storage (NTFS)
grepai.exe ──HTTP──> Ollama (localhost:11434)
```

#### Rozložení na disku (návrh)

```
%LOCALAPPDATA%\code-intel\qdrant\bin\<verze>\qdrant.exe
%LOCALAPPDATA%\code-intel\qdrant\storage\
%LOCALAPPDATA%\code-intel\qdrant\snapshots\
%LOCALAPPDATA%\code-intel\qdrant\qdrant.log
%LOCALAPPDATA%\code-intel\qdrant\qdrant.pid
```

- Binárka **není** v `%USERPROFILE%\.local\lib\agent-code-intel`. Upgrade
  produktu ten adresář nahrazuje celý [kód: install.py:207], takže by smazal
  binárku i data [odvozeno].
- `%LOCALAPPDATA%` je neroamingový profil, vhodný pro velká data [neověřeno:
  firemní politiky roamingu].

#### Spuštění

qdrant čte konfiguraci ze zabudovaného `config/config.yaml`, pak z
`config/config`, `config/<RUN_MODE>` a `config/local` relativně k pracovnímu
adresáři, z `--config-path` a nakonec z proměnných prostředí s prefixem
`QDRANT` a oddělovačem `__` [ověřeno: S27, `src/settings.rs`]. Výchozí hodnoty:
`service.host: 0.0.0.0`, `http_port: 6333`, `grpc_port: 6334`,
`storage.storage_path: ./storage`, `telemetry_disabled: false` [ověřeno: S27,
`config/config.yaml`].

Produkt proto spouští proces takto:

| Nastavení | Hodnota | Důvod |
| --- | --- | --- |
| pracovní adresář | `%LOCALAPPDATA%\code-intel\qdrant` | relativní `config/*` se nenajdou; žádná cizí konfigurace |
| `QDRANT__SERVICE__HOST` | `127.0.0.1` | výchozí `0.0.0.0` by qdrant otevřel do sítě |
| `QDRANT__SERVICE__HTTP_PORT` | `qdrant_http_port` z konfigurace [kód: config.py:80] | shoda s dnešními klíči |
| `QDRANT__SERVICE__GRPC_PORT` | `qdrant_port` z konfigurace [kód: config.py:81] | totéž |
| `QDRANT__STORAGE__STORAGE_PATH` | absolutní cesta `storage` | nezávislost na pracovním adresáři |
| `QDRANT__STORAGE__SNAPSHOTS_PATH` | absolutní cesta `snapshots` | totéž |
| `QDRANT__TELEMETRY_DISABLED` | `true` | stack má běžet jen lokálně |
| stdout a stderr | `qdrant.log` | diagnostika v dashboardu |
| `creationflags` | `DETACHED_PROCESS \| CREATE_NEW_PROCESS_GROUP` | proces přežije zavření terminálu [ověřeno: S22; přežití odhlášení neověřeno] |

- Zda Windows Defender Firewall zobrazí dotaz i při `127.0.0.1`, je
  [neověřeno].
- Po startu produkt čeká na `/healthz` a otevřený gRPC port s timeoutem, stejně
  jako u kontejneru [kód: integrations.py:160–193].

#### Kdy se qdrant spouští

- `--apply` a `--refresh` (bootstrap): když health selže, spustí `qdrant.exe`.
  Stejný vzor dnes platí pro `ollama serve` [kód: integrations.py:293–299].
- `--status` a `--status --json` nic nespouští, jako dnes
  [kód: integrations.py:79–84 komentář].
- Po restartu Windows qdrant neběží, dokud ho něco nespustí. To odpovídá
  dnešnímu chování GrepAI watcheru na macOS: README říká, že po restartu je
  nutné spustit `--refresh` [README, kapitola 13].
- **Automatický start po přihlášení (Q16).** Zvažované varianty:

| Varianta | Administrátor | Poznámka |
| --- | --- | --- |
| jen na vyžádání (`--refresh`) | ne | MCP hledání v nové session selže, dokud neproběhne `--refresh` |
| položka ve složce Po spuštění | [neověřeno] ne | nutné skryté okno (`pythonw.exe` nebo jiný launcher bez konzole) [neověřeno] |
| úloha v Plánovači úloh „při přihlášení“ | [neověřeno] | spolehlivější restart po pádu [neověřeno] |
| služba Windows (NSSM, WinSW) | ano | běží i bez přihlášení; nástroj třetí strany |

  **Rozhodnuto (Q16):** bootstrap na vyžádání vždy, plus volitelná položka ve
  složce Po spuštění, kterou `--install-deps` nabídne s potvrzením.

  Upřesnění návrhu:

  - Položku zapíše `--install-deps` jen s TTY a po odpovědi `y`. Bez TTY
    vypíše ruční postup, stejně jako u Homebrew [kód: commands.py:295–304].
  - Položka spouští qdrant se stejnými proměnnými jako bootstrap. Produkt
    položku vlastní a pozná ji podle značky v obsahu, podobně jako managed
    bloky v `CLAUDE.md`.
  - Když qdrant už běží, položka nic nespustí podruhé (kontrola portu nebo
    `/healthz` před startem).
  - Odinstalace v README položku odstraní.
  - **Ověřit ve fázi 0:** zápis bez administrátora, spuštění bez viditelného
    okna a přesný formát položky (zástupce `.lnk`, `.cmd` nebo jiný launcher).
    Pokud položka ve složce Po spuštění nepůjde bez viditelného okna, vrátit
    se k rozhodnutí a porovnat s Plánovačem úloh.

#### Instalace a verze

- Produkt připne verzi a SHA-256 zip souboru (např. 1.19.1 a digest
  `9b6f69bd…` z GitHub API [ověřeno: S27]).
- **Rozhodnuto (Q15):** binárku stáhne `--install-deps`. Na Windows:
  1. zjistí, že připnutá verze v `bin\<verze>` chybí;
  2. s TTY nabídne `[y/N]`, bez TTY jen vypíše URL, očekávaný SHA-256 a ruční
     postup a vrátí 1, jako dnes u chybějících nástrojů
     [kód: commands.py:252–310];
  3. stáhne zip z GitHub releases přes `urllib` do dočasného souboru;
  4. ověří SHA-256 proti hodnotě v kódu produktu; při neshodě soubor smaže a
     skončí `[ERROR: …]`;
  5. rozbalí přes `zipfile` do dočasného adresáře a přesune ho na
     `bin\<verze>`;
  6. nabídne položku ve složce Po spuštění (Q16).

  Ruční stažení podle README zůstává pro stroje bez přístupu na GitHub.
- **Upgrade qdrant nesmí přeskočit minor verzi, ani na jednom uzlu.** Mezi
  verzemi je nutné projít poslední patch každé mezilehlé minor verze
  [ověřeno: S28].
- Důsledek: produkt zná seznam podporovaných verzí. Když zjistí na disku
  starší data a nová verze je o víc než jednu minor verzi výš, upgrade odmítne
  a vypíše kroky. Jak zjistit verzi dat nebo běžícího procesu (`qdrant.exe
  --version`, `GET /`), je [neověřeno].
- Stará verze binárky zůstává v `bin\<verze>` pro návrat zpět.

#### Změny v kódu

- Nový klíč `qdrant_runtime` s hodnotami `container` a `native`. Profil Windows
  má `native` a jinou hodnotu odmítne. macOS má `container`.
- Nový adaptér `integrations.QdrantNative`: `installed_version`, `start`,
  `pid_alive`, `stop` (jen pro odinstalaci). Stávající `container_*` metody se
  nemění.
- Bootstrap v `commands.py` se ptá profilu, který adaptér použít.
- `--status --json` na Windows: `services.container.cli` je prázdný a přibude
  `services.qdrant_native` s klíči `binary`, `version`, `pid`, `running`.
  Nový JSON klíč je viditelná změna pro CHANGELOG.
- Dashboard: řádek „docker“ se na Windows nahradí řádkem „qdrant process“
  [kód: code-intel-dash:1312–1322 čte `svc.container`].
- Klíče `qdrant_container`, `qdrant_volume` a `qdrant_image` se na Windows
  ignorují.

#### Preflight na Windows

| Kontrola | Výsledek při chybě |
| --- | --- |
| `qdrant.exe` připnuté verze existuje | `MISSING` + `agent-code-intel --install-deps` |
| port 6333 nebo 6334 obsazený jiným procesem | `MISSING` s názvem procesu, pokud jde zjistit [neověřeno] |
| data starší o víc než jednu minor verzi | `MISSING` s postupem upgradu (S28) |
| health po startu | `MISSING` + posledních 20 řádků `qdrant.log` |

#### Odstranění

- `--remove --purge-collection` maže kolekci přes HTTP jako dnes
  [kód: integrations.py:337–347].
- Odinstalace stacku v README: zastavit proces (`Stop-Process -Name qdrant`),
  odstranit položku automatického startu a smazat
  `%LOCALAPPDATA%\code-intel\qdrant`.

---

## 7. Strategie: varianty a doporučení

| Varianta | Popis | Pro | Proti |
| --- | --- | --- | --- |
| **A. Nativní Windows** (zvoleno) | všechno ve Windows včetně nativního `qdrant.exe` | uživatel pracuje v PowerShellu a VS Code; Claude Code i Codex jsou nativní [ověřeno: S14, S16]; bez virtualizace a bez licence; kód je jeden | nejvíc změn v kódu (kapitola 5); správa binárky qdrant (6.12) |
| B. Jen WSL 2 | celý stack a projekty uvnitř distribuce Linuxu; Windows jen jako hostitel | skoro žádné změny kódu, pokud funguje Linux | Linux dnes není oficiálně podporovaný [README: platform macOS]; projekty musí být ve WSL FS; uživatel Windows editorů má dvojí svět |
| C. Hybrid | CLI a agenti ve Windows, služby (qdrant, Ollama) ve WSL | — | nejsložitější síť a diagnostika; bez jasné výhody proti A |

**Rozhodnutí: A.** Zadání chce instalátor a nástroje spustitelné na Windows,
použitelné pro firemní vývoj a bez služeb, které se samy vypínají. Varianty B a
C závisí na WSL, a to výchozí nastavení vypíná [ověřeno: S25]. Varianta B je
vhodný pozdější doplněk („Linux podpora“), protože `HostProfile` s hodnotou
`linux` ji připraví.

---

## 8. Plán implementace

Každá fáze je samostatně mergovatelná vertikální změna s vlastním PR.
macOS chování se v žádné
fázi nesmí změnit, kromě odstranění `curl` ve fázi 2.

Před každou editací platí pravidla repozitáře: `impact` analýza GitNexus,
`detect_changes` před commitem, CHANGELOG a kontrola README.

### Fáze 0 — ověřovací spike na reálném Windows

**Cíl:** Potvrdit nebo vyvrátit předpoklady označené [neověřeno] a [odvozeno]
dřív, než se změní produkční kód. Provádí ji agent na Windows 11 x64 podle
[kapitoly 15](#15-fáze-0-runbook-pro-agenta-na-windows-11). Výstupem je soubor
`docs/plans/windows-support-phase0-results.md` s verdiktem GO / NO-GO; kód
v `agent_code_intel/` se nemění.

**Hotovo, když:** splněno kritérium „Hotovo, když“ z kapitoly 15.7.

### Fáze 1 — platformní profil a detekce OS

- Modul `hostos.py`, `detect()`, `HostProfile` pro `darwin` a `windows`.
- Předání profilu z `cli.main` do režimů. `run_install_deps` přejde z parametru
  `system` na profil.
- Nepodporované OS nebo ARM64 na Windows: čitelná chyba.
- **Beze změny chování na macOS.**
- **Akceptace:** unit testy s oběma profily; `test/unit.sh` zelený na macOS.

### Fáze 2 — spouštění nástrojů a HTTP bez `curl`

- `resolve_executable` a jeho použití v `Stack`, `CommandRunner`, `_real_spawn`.
- `gitnexus` přes `node` + skript na Windows.
- Odpojené procesy na pozadí.
- `qdrant_http_ok` a `qdrant_collection_delete` přes `urllib`.
- **Viditelné:** `curl` už není povinná závislost. CHANGELOG a README.
- **Akceptace:** testy seamů s falešným `which` pro `.cmd`; na Windows CI test,
  který spustí skutečný `.cmd` soubor.

### Fáze 3 — instalátor produktu na Windows

- `.cmd` shimy, `launcher.py` v `lib`, kontrola PATH přes `os.pathsep`, rada
  pro PowerShell, domov z `USERPROFILE`.
- `defaults.env` na Windows: chyba s radou.
- **Akceptace:** na Windows CI `python agent-code-intel --install` do dočasného
  `USERPROFILE`, pak spuštění `agent-code-intel.cmd --version`.

### Fáze 4 — `--install-deps` a preflight pro Windows

- winget mapování, volitelně Scoop, ruční příkazy pro grepai a gitnexus.
- Preflight kontroly: VC++ Redistributable, OpenSSL DLL, Git Bash.
- Platformní rady (`node_upgrade_hint`).
- **Akceptace:** unit testy výstupu pro profil Windows bez TTY a s TTY
  (falešný stdin), stejné exit kódy jako macOS.

### Fáze 5 — cesty, hooky a MCP

- `same_path` a náhrada porovnání cest; registr; hash s normalizací konců
  řádků.
- Hint hook v Node, exec form pro Claude, `commandWindows` pro Codex.
  Migrace staré registrace při `--apply` a úklid při `--remove`.
- MCP `cmd /c gitnexus mcp` na Windows; `--status` přijme obě varianty.
- **Viditelné:** nový tvar hooku i na macOS. CHANGELOG a README (tabulka
  souborů po `--apply`).
- **Akceptace:** unit testy migrace hooku; ruční test v Claude Code a Codex na
  macOS i Windows.

### Fáze 6 — dashboard na Windows

- Nalezení launcheru, procesy přes CIM, logy, npm root, rady.
- **Akceptace:** `code-intel-dash --once` na Windows vrátí JSON a exit kód 0
  na zdravém stacku; unit testy parseru CIM výstupu.

### Fáze 7 — nativní qdrant na Windows

- Klíč `qdrant_runtime`, adaptér `QdrantNative`, bootstrap podle profilu.
- `--install-deps` stáhne připnutou verzi a ověří SHA-256 (Q15).
- Kontrola minor verze dat při upgradu.
- Volitelná položka ve složce Po spuštění s potvrzením (Q16).
- `--status --json` s `services.qdrant_native`; řádek v dashboardu.
- **Beze změny chování na macOS.**
- **Viditelné:** nový JSON klíč, nový klíč konfigurace. CHANGELOG a README.
- **Akceptace:** unit testy adaptéru s falešným spawn a HTTP; ruční test na
  Windows podle fáze 0 bodu 6 včetně restartu Windows.

### Fáze 8 — dokumentace, CI a akceptace

- README pro Windows, troubleshooting, badge.
- GitHub Actions matrix.
- Akceptační dokument `docs/acceptance/<verze>.md` podle vzoru existujících:
  čistý Windows 11 x64, projekt s `--agent both`, `--apply`, `--refresh`,
  `--status --all`, `--remove --apply`, dashboard, hledání v Claude Code.
- **Verze (rozhodnuto, Q9):** minor release 6.x. Podmínka: starší verze
  nástroje novou registraci hooku jen ignoruje jako cizí a nic nerozbije. Fáze 5
  to musí ověřit testem; když podmínka neplatí, rozhodnutí znovu otevřít.

### Závislosti fází

```
0 ──> 1 ──> 2 ──> 3 ──> 4 ──> 7 ──> 8
            │                     ^
            └──> 5 ──> 6 ─────────┘
```

---

## 9. Rizika

| # | Riziko | Dopad | Zmírnění |
| --- | --- | --- | --- |
| R1 | GitNexus na Windows má nativní problémy (FTS, prebuildy) | graf nebo keyword search nefunguje | preflight kontroly (6.4), `--repair-fts` v README, fáze 0 bod 4 |
| R2 | Instalace qdrant z binárky na Windows není v dokumentaci qdrant popsaná [S2] | nečekané chování, které CI qdrant nezachytí | připnutá verze; akceptační test na Windows pro každou verzi; důkazy z CI a NTFS kontroly [S27] |
| R3 | Codex spuštěný z podadresáře nenajde hook skript (Q3) | hint v té session chybí | README: spouštět Codex z kořene; hint je jen doplněk k `AGENTS.md` a skills; fáze 0 bod 8 |
| R4 | `.cmd` shim a parsování `%*` | argumenty se speciálními znaky se rozbijí | CLI nemá volný text v argumentech; Q4 (`.exe` launcher) |
| R5 | Změna hooku z Pythonu na Node | stávající projekty mají starou registraci | migrace v `--apply`, detekce staré registrace jako vlastní |
| R6 | `os.replace` selže, když cílový soubor drží jiný proces (antivir, watcher, editor) | `--apply` skončí chybou | krátký retry s čekáním jen na Windows [neověřeno, zda je nutný] |
| R7 | Windows Defender zpomalí indexaci (`.grepai`, `.gitnexus`) | pomalý `--refresh` | [neověřeno]; zmínit výjimku v troubleshootingu až po měření |
| R8 | Nástroje bez aktuálních Windows buildů (`tokei`, `rga`) | slabší code-context | jsou jen „strongly recommended“; hint může na Windows nabídnout `scc` |
| R9 | Rozdílný `HOME` v Git Bash vs PowerShell | jiná konfigurace podle shellu | `USERPROFILE` na Windows (6.7) |
| R10 | Windows ARM64 | GitNexus nejde nainstalovat | jasná chyba v preflightu; sledovat `@ladybugdb/core` |
| R11 | Upgrade qdrant nesmí přeskočit minor verzi [S28] | poškozená nebo nečitelná data po velkém skoku verzí | připnuté verze; kontrola verze dat; postup upgradu po krocích (6.12) |
| R12 | qdrant po restartu Windows neběží | MCP hledání selže, dokud neproběhne `--refresh` | bootstrap na vyžádání; volitelná položka ve složce Po spuštění (Q16) |
| R13 | Windows Defender skenuje `storage` a zpomalí qdrant | pomalá indexace | změřit ve fázi 0; případná výjimka až po měření a jen s poučením uživatele |
| R14 | Port 6333 nebo 6334 obsazený (např. Docker Desktop s qdrant) | qdrant nenaběhne | preflight kontrola portu (6.12) |
---

## 10. Rozhodnutí

Rozhodnuto uživatelem 2026-09-17.

| # | Otázka | Původní doporučení | Rozhodnutí |
| --- | --- | --- | --- |
| Q1 | Jak provozovat qdrant na Windows? | Docker Desktop | **nativní `qdrant.exe`** (6.12); dřívější volba Docker Engine ve WSL 2 zrušena kvůli vypínání a firemnímu použití |
| Q2 | Implementovat nativní `qdrant.exe` (fáze 7) už v první verzi? | ne | **ano**, plyne z Q1 |
| Q3 | Tvar `commandWindows` pro Codex hook | relativní cesta | **`node .claude/helpers/code-context-hint.mjs`** (6.5); z podadresáře hint chybí |
| Q4 | `.cmd` shim, nebo `.exe` launcher (pipx/uv, `console_scripts`)? | `.cmd` | **`.cmd` shim** |
| Q5 | Skills a hint pro Codex v PowerShellu | jen Bash + Git Bash | **jen Bash + Git Bash**; PowerShell varianty později |
| Q6 | Oprávnění `agent-code-intel --refresh` pro PowerShell tool Claude Code | Bash i PowerShell | **na Windows `Bash(…)` i `PowerShell(…)`** (6.1); macOS beze změny |
| Q7 | Adresář konfigurace | `%USERPROFILE%\.config\code-intel` | **`%USERPROFILE%\.config\code-intel`** |
| Q8 | Zapisovat `.gitattributes` do cílových projektů? | ne | **ne** |
| Q9 | Verze: minor, nebo major? | minor | **minor 6.x** (s podmínkou v fázi 8) |
| Q10 | Windows ARM64 částečně bez GitNexus? | ne | **nepodporovat** |
| Q11 | Umístění instalace na Windows | `%USERPROFILE%\.local` | **`%USERPROFILE%\.local\bin` a `.local\lib`** |
| Q12 | Hint hook: Node, nebo Python? | Node | **Node** (6.5) |
| Q13 | Odstranit `curl` jako závislost na všech OS? | ano | **ano, `urllib`** (6.3) |
| Q14 | `defaults.env` na Windows? | nepodporovat | **nepodporovat** (6.7) |
| Q15 | Kdo stáhne `qdrant.exe`? | `--install-deps` s ověřením SHA-256 | **`--install-deps` s ověřením SHA-256**; ruční postup v README jako záloha |
| Q16 | Automatický start qdrant po přihlášení | na vyžádání + volitelná položka ve složce Po spuštění | **na vyžádání + volitelná položka ve složce Po spuštění**; mechanismus ověřit ve fázi 0 |

---

## 11. Co v průzkumu chybí

Tyto informace se nepodařilo ověřit a plán na nich závisí:

1. Zda je `curl.exe` součástí všech podporovaných verzí Windows. Návrh 6.3 tuto
   otázku ruší.
2. Zda je shell session Codexu na Windows PowerShell, nebo `cmd.exe`
   (mechanismus výběru ověřen ve zdrojích, S31).
3. Zda je nativní Windows podpora Codexu stále experimentální.
4. Chování `winget install` s více id v jednom příkazu.
5. Balíček `scc` ve winget (hledání v `microsoft/winget-pkgs` nenašlo manifest
   pod `boyter` ani `benboyter`; code search API vrátilo prázdný výsledek).
6. Přesný název spustitelného souboru tray aplikace Ollama.
7. Formát `CreationDate` z `Get-CimInstance … | ConvertTo-Json`.
8. Zda `os.path.realpath` na Windows vrací velikost písmen z disku.
9. Chování `ctags` s `TMPDIR` na Windows.
10. Zda `qdrant.exe` přežije odhlášení uživatele při `DETACHED_PROCESS`.
11. Zda Windows Defender Firewall zobrazí dotaz při `127.0.0.1`.
12. Jak zjistit verzi `qdrant.exe` a verzi uložených dat.
13. Zda položka ve složce Po spuštění a úloha v Plánovači úloh fungují bez
    administrátora a bez viditelného okna.
14. Vliv Windows Defender na výkon qdrant.
15. Podpora qdrant pro instalaci z binárky na Windows mimo CI testy.
16. Zda pravidlo `PowerShell(agent-code-intel --refresh)` pokryje volání
    `agent-code-intel.cmd`.

Bod 1 je vyřešen rozhodnutím Q13. Otázky kolem Docker Desktop a WSL odpadly
rozhodnutím Q1. Ostatní body ověřuje runbook v kapitole 15:

| Bod | Test |
| --- | --- |
| 1 | T03 |
| 2 | T24 |
| 3 | mimo runbook (dokumentace Codexu) |
| 4 | T28 |
| 5 | T28 |
| 6 | T11 |
| 7 | T29 |
| 8 | T06 |
| 9 | T28 |
| 10 | T05, H2 |
| 11 | T14 |
| 12 | T14, T16 |
| 13 | H2 |
| 14 | T17 |
| 15 | T13–T16 |
| 16 | T20 |

---

## 12. Kontrolní seznam pro reviewera

- [x] Souhlas se strategií A (kapitola 7).
- [x] Rozhodnutí Q1–Q16.
- [x] Souhlas s odstraněním `curl` jako závislosti (6.3).
- [x] Souhlas se změnou hint hooku na Node (6.5).
- [x] Souhlas s tím, že `defaults.env` na Windows nebude podporovaný (6.7).
- [ ] Přidělení stroje s Windows 11 x64 pro fázi 0; Windows 10 22H2 x64 pro
  kontrolní běh.

---

## 13. Příloha: navrhovaná instalační cesta pro Windows (koncept README)

Koncept, ne finální text. Každý příkaz bude ověřen ve fázi 0.

```powershell
# 1. Základ (PowerShell, běžný uživatel)
winget install --id Git.Git -e
winget install --id Python.PythonInstallManager -e
winget install --id OpenJS.NodeJS.LTS -e
winget install --id Ollama.Ollama -e
winget install --id Microsoft.VCRedist.2015+.x64 -e

# 2. qdrant.exe stáhne a ověří agent-code-intel --install-deps (krok 4)
#    a nabídne automatický start po přihlášení

# 3. Nástroje stacku
irm https://raw.githubusercontent.com/yoanbernabeu/grepai/main/install.ps1 | iex
npm i -g gitnexus

# 4. Produkt
git clone https://github.com/eduardtomasek/agent-code-intel.git $env:USERPROFILE\src\agent-code-intel
cd $env:USERPROFILE\src\agent-code-intel
python .\agent-code-intel --install
agent-code-intel --install-deps

# 5. První projekt
mkdir $env:USERPROFILE\projects\my-project
cd $env:USERPROFILE\projects\my-project
agent-code-intel --agent both --apply
```

---

## 14. Zdroje

Všechny zdroje načteny 2026-09-17.

| Id | Zdroj | Co dokládá |
| --- | --- | --- |
| S1 | GitHub releases `qdrant/qdrant` v1.19.1 (`gh release view`) | `qdrant-x86_64-pc-windows-msvc.zip`; žádný Windows ARM64 asset |
| S2 | qdrant docs: [Installation — Storage](https://qdrant.tech/documentation/installation/), [Troubleshooting — Incompatible file system](https://qdrant.tech/documentation/common-errors/) (zdroj `qdrant/landing_page`) | POSIX FS; Docker/WSL mount a ztráta dat; pojmenovaný svazek |
| S3 | [yoanbernabeu/grepai](https://github.com/yoanbernabeu/grepai): README, `install.ps1`, `daemon/daemon.go`, `daemon/daemon_windows.go`; release v0.37.0 | Windows zipy (amd64, arm64); `install.ps1` a jen amd64; `%LOCALAPPDATA%\grepai\logs`; Windows démon |
| S4 | [Ollama for Windows](https://docs.ollama.com/windows) | Windows 10 22H2+, Home/Pro; bez administrátora; běh na pozadí; `localhost:11434`; NSSM |
| S5 | README balíčku `gitnexus` 1.6.12 (npm tarball) | MCP `cmd /c` na Windows; VC++ Redistributable a OpenSSL 3 pro FTS; `--repair-fts` |
| S6 | npm tarbally `gitnexus@1.6.12`, `@ladybugdb/core@0.18.3`, `tree-sitter@0.21.1`; `npm view gitnexus` | `engines`, `bin`; prebuildy `win32-x64`/`win32-arm64` pro gramatiky; LadybugDB jen `win32-x64` |
| S7 | GitHub releases `BurntSushi/ripgrep` 15.2.0, `sharkdp/fd` v10.5.0 | Windows zipy x64, x86, ARM64 |
| S8 | GitHub releases `universal-ctags/ctags-win32` v6.1.0 | Windows buildy x64 a x86 |
| S9 | GitHub releases `ast-grep/ast-grep` 0.45.3 | Windows zipy x64, x86, ARM64 |
| S10 | GitHub releases `XAMPPRocky/tokei` v13–v15, `boyter/scc` v4.1.0; Scoop Main `tokei.json`, `scc.json` | tokei bez Windows assetů; Scoop tokei 12.1.2; scc Windows zipy |
| S11 | GitHub releases `phiresky/ripgrep-all` v0.10.10; Scoop Main `rga.json` | v0.10.10 bez Windows; Scoop 0.10.9 a závislosti |
| S12 | [Install Docker Desktop on Windows](https://docs.docker.com/desktop/setup/install/windows-install/) | požadavky, WSL ≥ 2.1.5, licence, ARM Early Access |
| S13 | GitHub releases `ollama/ollama` v0.34.1 | `OllamaSetup.exe`, `ollama-windows-amd64.zip`, `ollama-windows-arm64.zip` |
| S14 | [Claude Code — Advanced setup](https://code.claude.com/docs/en/setup) | Windows požadavky; Git for Windows a Git Bash; PowerShell tool; `%USERPROFILE%\.local\bin\claude.exe`; winget `Anthropic.ClaudeCode` |
| S15 | [Claude Code — Hooks reference](https://code.claude.com/docs/en/hooks) | shell form (Git Bash / PowerShell), pole `shell`, exec form `args`, `.cmd` shimy nejdou v exec form, vzor `node` + skript |
| S16 | [Codex — Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox) | nativní běh v PowerShellu; WSL jen pro linuxový toolchain |
| S17 | [Codex — Hooks](https://learn.chatgpt.com/docs/hooks) | `commandWindows` / `command_windows`; `cwd`; resoluce od kořene gitu |
| S18 | [Using Python on Windows](https://docs.python.org/3/using/windows.html) | Python install manager; `python`, `py`, `python3`; App execution aliases; zastaralý klasický instalátor |
| S19 | [Accessing network applications with WSL](https://learn.microsoft.com/en-us/windows/wsl/networking) | `localhost` z Windows do WSL 2 v režimu NAT; mirrored mode |
| S20 | [CreateProcessW](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw) | doplnění jen `.exe`; batch soubory přes `cmd.exe /c` |
| S21 | [microsoft/winget-pkgs](https://github.com/microsoft/winget-pkgs) — adresáře `manifests/` (GitHub API) | existence a verze balíčků: `Git.Git`, `Python.PythonInstallManager`, `OpenJS.NodeJS.LTS`, `Docker.DockerDesktop`, `RedHat.Podman-Desktop`, `SUSE.RancherDesktop`, `Ollama.Ollama`, `BurntSushi.ripgrep.MSVC`, `sharkdp.fd`, `UniversalCtags.Ctags`, `ast-grep.ast-grep`, `Microsoft.VCRedist.2015+.x64`, `Anthropic.ClaudeCode`, `OpenAI.Codex` |
| S22 | [subprocess — Python docs](https://docs.python.org/3/library/subprocess.html) | resoluce spustitelného souboru na Windows; `env` neovlivní hledání v PATH; batch soubory a escapování; `DETACHED_PROCESS`, `CREATE_NEW_PROCESS_GROUP`; `start_new_session` jen POSIX |
| S23 | [npm — folders](https://docs.npmjs.com/cli/v11/configuring-npm/folders) | globální prefix `%AppData%\npm`; spustitelné soubory přímo v prefixu |
| S24 | [Use systemd to manage Linux services with WSL](https://learn.microsoft.com/en-us/windows/wsl/systemd) | systemd výchozí pro Ubuntu z `wsl --install`; WSL 0.67.6+; služby systemd instanci WSL nedrží naživu |
| S25 | [Advanced settings configuration in WSL](https://learn.microsoft.com/en-us/windows/wsl/wsl-config) | `instanceIdleTimeout` 15000 ms a `-1`; `vmIdleTimeout` jen Windows 11; `localhostForwarding` výchozí `true`; `[boot]` jen Windows 11 a Server 2022; `[boot] command=service docker start` |
| S26 | [Install Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/) | instalace z apt repozitáře; odkaz na Linux post-install pro skupinu `docker`; WSL stránka nezmiňuje |
| S27 | [qdrant/qdrant](https://github.com/qdrant/qdrant) (shallow clone, GitHub API): `src/settings.rs`, `config/config.yaml`, `lib/common/common/src/fs/check.rs`, `.github/workflows/rust.yml`, `.github/workflows/release-artifacts.yml`, licence, release v1.19.1; licence `rancher-sandbox/rancher-desktop` a `containers/podman-desktop` | pořadí konfigurace a prefix `QDRANT`/`__`; výchozí host, porty, storage, telemetrie; NTFS `Good`; Windows v CI a release; Apache-2.0; SHA-256 digest zipu |
| S28 | [qdrant — Upgrades](https://qdrant.tech/documentation/upgrades/) (zdroj `qdrant/landing_page`) | upgrade přes poslední patch každé minor verze, i pro jeden uzel |
| S29 | [Podman Desktop — Windows](https://podman-desktop.io/docs/installation/windows-install) | WSL 2 nebo Hyper-V; administrátor; Hyper-V jen Pro/Enterprise |
| S30 | [pgvector README — Windows](https://github.com/pgvector/pgvector) | build přes Visual Studio a `nmake` jako administrátor |
| S31 | [openai/codex](https://github.com/openai/codex) commit `e269f21` (2026-09-17): `codex-rs/hooks/src/engine/discovery.rs`, `codex-rs/hooks/src/engine/command_runner.rs`, `codex-rs/core/src/session/mod.rs` | `command_windows` má na Windows přednost; shell session, jinak `%COMSPEC%` `/C` (`cmd.exe`) |
| S32 | [Claude Code — Tools reference](https://code.claude.com/docs/en/tools-reference) | PowerShell tool; pravidla oprávnění `PowerShell(<vzor>)` |

---

## 15. Fáze 0: runbook pro agenta na Windows 11

Tuto kapitolu provádí agent (Claude Code nebo Codex) na stroji s Windows 11 x64.
Cíl: potvrdit nebo vyvrátit každý předpoklad, na kterém stojí plán podpory
Windows, a výsledky zapsat tak, aby šlo bez dalšího hádání rozhodnout, jestli
a jak podporu implementovat.

Kapitoly 1–14 jsou kontext: co a proč se testuje. Tato kapitola říká, jak.

### 15.1 Pravidla provedení

- **Produkt neměň.** Nic v `agent_code_intel/`, `agent-code-intel`,
  `code-intel-dash` ani v testech. Jediný soubor v repozitáři, který vzniká, je
  soubor výsledků (15.4).
- **Všechno ostatní dělej v pracovním adresáři** `%USERPROFILE%\aci-phase0`
  (dál jen `$W`). Testovací projekty, skripty, stažené soubory i výstupy patří
  sem.
- **Každý test končí stavem** `PASS`, `FAIL`, `PARTIAL` nebo `BLOCKED`.
  `BLOCKED` vždy s důvodem a s tím, co by test odblokovalo. Výsledek, který jsi
  neviděl ve výstupu, nezapisuj; označ ho `BLOCKED`.
- **Zapisuj fakta, ne dojmy.** U každého testu: přesné příkazy, zkrácený
  rozhodující výstup (max. ~30 řádků, doslovně), návratové kódy, verze nástrojů.
- **Kroky pro člověka.** Některé kroky vyžadují člověka (UAC, přihlášení,
  dialog firewallu, odhlášení, restart, schválení hooku). U nich se zastav,
  napiš člověku přesný pokyn a počkej na potvrzení. Seznam je v 15.3.
- **Obnovitelnost.** Odhlášení a restart ukončí tvou session. Proto soubor
  výsledků ukládej po každém testu. Po návratu soubor načti a pokračuj prvním
  testem bez stavu.
- **Pořadí.** Testy spouštěj v pořadí z 15.5, s jedinou výjimkou: T04
  potřebuje `gitnexus` z T09, proto proveď T08 a T09 před T04. Testy ve
  skupině H (odhlášení, restart) jsou záměrně na konci.
- **Commit.** Na konci připrav commit jen se souborem výsledků do nové větve
  `research/windows-phase0` a řiď se pravidly repozitáře v `AGENTS.md` a
  `CLAUDE.md`. Commituj a pushuj jen po výslovném souhlasu člověka.

### 15.2 Jak spouštět příkazy

Proměnné PowerShellu mezi voláními nástroje nepřežijí a po instalaci přes winget
má běžící proces zastaralý `PATH`. Proto:

1. Každý PowerShell blok z této kapitoly ulož do `$W\scripts\<ID>.ps1`. Na
   začátek každého souboru vlož **společnou hlavičku**:

   ```powershell
   $ErrorActionPreference = 'Continue'
   $W = "$env:USERPROFILE\aci-phase0"
   $R = "$env:USERPROFILE\src\agent-code-intel"
   $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' +
               [Environment]::GetEnvironmentVariable('Path','User')
   New-Item -ItemType Directory -Force "$W\scripts","$W\out" | Out-Null
   ```

   Když je checkout jinde než v `$env:USERPROFILE\src\agent-code-intel`, uprav
   `$R` a zapiš skutečnou cestu do výsledků (T00).
2. Spusť ho takto (z PowerShellu i z Git Bash):

   ```
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%USERPROFILE%\aci-phase0\scripts\<ID>.ps1" > "%USERPROFILE%\aci-phase0\out\<ID>.txt" 2>&1
   ```

   V Git Bash použij cestu `"$USERPROFILE/aci-phase0/..."`. Pak přečti
   `out\<ID>.txt`.
3. Python soubory z této kapitoly ulož do `$W\scripts\` pod uvedeným názvem.
4. Bloky označené **[člověk]** neprováděj sám.

### 15.3 Předpoklady a kroky pro člověka

**Než člověk agenta spustí** (jednorázově, ručně):

1. Windows 11 x64 s internetem. Účet s možností potvrdit UAC.
2. Git for Windows: `winget install --id Git.Git -e`.
3. Agent, který runbook provede: Claude Code
   (`irm https://claude.ai/install.ps1 | iex`) nebo Codex
   (`winget install --id OpenAI.Codex -e`). Přihlášení do agenta.
4. `git clone https://github.com/eduardtomasek/agent-code-intel.git $env:USERPROFILE\src\agent-code-intel`
5. Agent spuštěný v kořeni checkoutu s pokynem provést kapitolu 15 dokumentu
   `docs/plans/windows-support.md`.

**Během běhu agent požádá člověka o:**

| Kdy | Co člověk udělá |
| --- | --- |
| T01, T13, T28 | potvrdí UAC dialogy instalátorů winget, pokud se objeví |
| T14 | řekne, jestli se objevil dialog Windows Defender Firewall, a zvolí „Zrušit“ |
| T21–T23 | přihlásí Claude Code, pokud agent běží v Codexu |
| T24 | přihlásí Codex, důvěřuje projektu a schválí hooky přes `/hooks` |
| H1 | zavře okno konzole křížkem |
| H2 | odhlásí se a znovu přihlásí |
| H3 | restartuje Windows |

### 15.4 Soubor výsledků

Vytvoř `docs/plans/windows-support-phase0-results.md` s touto kostrou a
vyplňuj ji průběžně:

```markdown
# Fáze 0: výsledky ověření na Windows 11

- Datum:
- Agent a verze:
- Checkout (cesta, commit):

## Prostředí (T00)

## Souhrn

| ID | Test | Stav | Jedna věta výsledku |
| --- | --- | --- | --- |

## Detail testů

### T00 …
- Stav:
- Příkazy:
- Rozhodující výstup:
- Závěr pro plán (odkaz na kapitolu / Q / N / neověřený bod):

## Verdikt (15.7)

## Navržené úpravy windows-support.md
```

Poslední sekce obsahuje konkrétní úpravy plánu: které značky [neověřeno] nahradit
jakým výsledkem a která rozhodnutí Q znovu otevřít. Samotný
`windows-support.md` neupravuj.

### 15.5 Testy

Každý test má **Cíl** (co ověřuje a proti čemu v plánu), **Kroky** a
**Vyhodnocení** (kdy je `PASS`).

#### A. Prostředí a instalace

**T00 — záznam prostředí**
- Cíl: kontext pro všechny ostatní výsledky.
- Kroky:
  ```powershell
  [System.Environment]::OSVersion.VersionString
  (Get-CimInstance Win32_OperatingSystem) | Select-Object Caption, Version, BuildNumber, OSArchitecture
  $env:PROCESSOR_ARCHITECTURE
  $PSVersionTable.PSVersion
  git --version
  git -C $R rev-parse HEAD
  ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
  Get-Command winget, claude, codex, python, py, node, npm -ErrorAction SilentlyContinue | Select-Object Name, Source
  ```
- Vyhodnocení: `PASS`, když je vše zapsané. Když architektura není `AMD64`,
  zapiš to a **ukonči runbook** (ARM64 je mimo rozsah, Q10).

**T01 — instalace základu přes winget**
- Cíl: 4.1, 13; potřeba administrátora.
- Kroky (po jednom, zapiš u každého, jestli se objevil UAC):
  ```powershell
  winget install --id Python.PythonInstallManager -e --accept-source-agreements --accept-package-agreements
  winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements
  winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements
  winget install --id Microsoft.VCRedist.2015+.x64 -e --accept-source-agreements --accept-package-agreements
  ```
  Pak v novém skriptu:
  ```powershell
  py list
  python --version
  py --version
  python3 --version
  node --version
  npm --version
  ollama --version
  ```
  Když `py list` nemá žádný runtime, zjisti postup z `py help` a nainstaluj
  nejnovější Python 3.x. Zapiš použitý příkaz.
- Vyhodnocení: `PASS`, když Python ≥ 3.11, Node ≥ 24.11.0 a `ollama` odpovídá.
  Zapiš, co dělá `python3` (běží, chybí, nebo otevře Microsoft Store).

**T02 — Git Bash a OpenSSL DLL**
- Cíl: 4.5 (FTS GitNexus), 6.5 (Git Bash povinný).
- Kroky:
  ```powershell
  Test-Path "C:\Program Files\Git\bin\bash.exe"
  Get-ChildItem "C:\Program Files\Git\mingw64\bin" -Filter "lib*-3-x64.dll" | Select-Object Name
  ```
- Vyhodnocení: `PASS`, když existuje `bash.exe`, `libssl-3-x64.dll` a
  `libcrypto-3-x64.dll`.

**T03 — `curl.exe`**
- Cíl: bod 1 kapitoly 11 (informativní; `curl` se má odstranit, Q13).
- Kroky: `Get-Command curl.exe | Select-Object Source; curl.exe --version`
- Vyhodnocení: `PASS` vždy; zapiš přítomnost a verzi.

#### B. Mechanika procesů a souborů v Pythonu

**T04 — resoluce `.cmd` shimu**
- Cíl: N3, N4, 6.2; S20, S22. Předpoklad: T09 krok `npm i -g gitnexus` už
  proběhl. Když ne, proveď nejdřív T09.
- Soubor `$W\scripts\t04_resolve.py`:
  ```python
  import json, os, shutil, subprocess
  res = {}
  def attempt(label, argv, **kw):
      try:
          p = subprocess.run(argv, capture_output=True, text=True, timeout=120, **kw)
          res[label] = {"rc": p.returncode, "out": p.stdout.strip()[:200], "err": p.stderr.strip()[:300]}
      except Exception as e:
          res[label] = {"exception": repr(e)}
  which = shutil.which("gitnexus")
  res["shutil_which"] = which
  attempt("bare_name", ["gitnexus", "--version"])
  if which:
      attempt("full_path_cmd", [which, "--version"])
      attempt("comspec_c", [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", which, "--version"])
  root = subprocess.run([os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", "npm", "root", "-g"],
                        capture_output=True, text=True).stdout.strip()
  res["npm_root_g"] = root
  attempt("node_script", ["node", os.path.join(root, "gitnexus", "dist", "cli", "index.js"), "--version"])
  res["expected_npm_root"] = os.path.join(os.environ["APPDATA"], "npm", "node_modules")
  print(json.dumps(res, indent=2))
  ```
  Spusť: `python "$W\scripts\t04_resolve.py"`.

  Druhá část, zda `env` ovlivní hledání v PATH (S22). Skript
  `$W\scripts\t04_envpath.py`:
  ```python
  import os, subprocess
  npm_dir = os.path.join(os.environ["APPDATA"], "npm")
  env = dict(os.environ)
  env["PATH"] = npm_dir + os.pathsep + env.get("PATH", "")
  try:
      p = subprocess.run(["gitnexus.cmd", "--version"], env=env, capture_output=True, text=True, timeout=120)
      print("rc", p.returncode, p.stdout.strip()[:200], p.stderr.strip()[:200])
  except Exception as e:
      print("exception", repr(e))
  ```
  Spusť ho s `PATH`, ze kterého je `npm` adresář odstraněný:
  ```powershell
  $env:Path = ($env:Path -split ';' | Where-Object { $_ -notlike '*\npm' -and $_ -notlike '*\npm\' }) -join ';'
  python "$W\scripts\t04_envpath.py"
  ```
- Vyhodnocení: `PASS`, když `bare_name` selže výjimkou nebo kódem ≠ 0,
  `full_path_cmd` nebo `comspec_c` projde a `node_script` projde. Zapiš, zda
  `t04_envpath.py` našel `gitnexus.cmd` (potvrzuje nebo vyvrací tvrzení z S22).

**T05 — odpojený proces přežije konec rodiče**
- Cíl: 6.2, 6.12 (`DETACHED_PROCESS`), bod 10 kapitoly 11.
- Soubor `$W\scripts\t05_spawner.py`:
  ```python
  import pathlib, subprocess, sys
  flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
  p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(3600)"],
                       creationflags=flags, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
  pathlib.Path(sys.argv[1]).write_text(str(p.pid))
  ```
  Kroky:
  ```powershell
  Start-Process powershell.exe -ArgumentList '-NoProfile','-Command',"python `"$W\scripts\t05_spawner.py`" `"$W\t05.pid`"" -Wait
  Start-Sleep 3
  Get-Process -Id (Get-Content "$W\t05.pid") -ErrorAction SilentlyContinue | Select-Object Id, ProcessName, StartTime
  ```
- Vyhodnocení: `PASS`, když proces po skončení rodičovského okna běží.
  Proces nech běžet pro H2 (odhlášení).

**T06 — `realpath` a velikost písmen**
- Cíl: 6.8, bod 8 kapitoly 11.
- Soubor `$W\scripts\t06_realpath.py`:
  ```python
  import os, pathlib
  W = pathlib.Path.home() / "aci-phase0"
  typed = str(W / "case-test" / "INNER")
  real = os.path.realpath(typed)
  print("realpath:", real)
  print("normcase:", os.path.normcase(typed))
  print("same_path:", os.path.normcase(real) == os.path.normcase(str(W / "Case-Test" / "Inner")))
  ```
- Kroky:
  ```powershell
  New-Item -ItemType Directory -Force "$W\Case-Test\Inner" | Out-Null
  python "$W\scripts\t06_realpath.py"
  ```
- Vyhodnocení: `PASS`, když `same_path` je `True`. Zapiš, zda `realpath`
  vrátil velikost písmen z disku (`Case-Test\Inner`).

**T07 — `os.replace` na souboru otevřeném jiným procesem**
- Cíl: 3.2, riziko R6.
- Soubor `$W\scripts\t07_hold.py`:
  ```python
  import pathlib, sys, time
  f = open(pathlib.Path.home() / "aci-phase0" / "t07-target.txt")
  time.sleep(30)
  ```
  Soubor `$W\scripts\t07_replace.py`:
  ```python
  import os, pathlib
  W = pathlib.Path.home() / "aci-phase0"
  (W / "t07-new.txt").write_text("new")
  try:
      os.replace(W / "t07-new.txt", W / "t07-target.txt")
      print("replaced")
  except Exception as e:
      print("failed", repr(e))
  ```
- Kroky:
  ```powershell
  Set-Content "$W\t07-target.txt" "old"
  $holder = Start-Process python -ArgumentList "`"$W\scripts\t07_hold.py`"" -PassThru
  Start-Sleep 3
  python "$W\scripts\t07_replace.py"
  Stop-Process -Id $holder.Id -ErrorAction SilentlyContinue
  ```
- Vyhodnocení: vždy `PASS` s popisem: projde `os.replace`, nebo vyhodí
  `PermissionError`? Výsledek rozhoduje, jestli je retry v 6.8 nutný.

#### C. GitNexus

**T08 — testovací projekt**
- Kroky:
  ```powershell
  New-Item -ItemType Directory -Force "$W\proj-a\src\sub" | Out-Null
  Set-Location "$W\proj-a"
  git init -q
  @'
  function checkCredentials(user, pass) {
    const hash = hashPassword(pass);
    return db.users.findOne({ name: user, hash });
  }
  function hashPassword(pass) { return pass.split('').reverse().join(''); }
  module.exports = { checkCredentials };
  '@ | Set-Content -Encoding utf8 "src\app.js"
  @'
  def parse_config(text):
      return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
  '@ | Set-Content -Encoding utf8 "src\sub\config.py"
  git add -A
  git -c user.name=phase0 -c user.email=phase0@example.invalid commit -qm "phase0 fixture"
  git log --oneline
  ```
- Vyhodnocení: `PASS`, když commit existuje.

**T09 — instalace a indexace GitNexus**
- Cíl: 4.5, R1, N3.
- Kroky:
  ```powershell
  npm i -g gitnexus 2>&1 | Select-Object -Last 40
  Get-Command gitnexus | Select-Object Name, Source
  gitnexus --version
  Set-Location "$W\proj-a"
  $t = Measure-Command { gitnexus analyze --embeddings 2>&1 | Out-File "$W\out\t09-analyze.txt" }
  "analyze seconds: $($t.TotalSeconds)"
  Get-Content "$W\out\t09-analyze.txt" -Tail 30
  gitnexus status
  gitnexus doctor
  ```
- Vyhodnocení: `PASS`, když `analyze` skončí úspěšně a `status` hlásí
  `up-to-date` nebo `up to date`. Když výstup obsahuje
  `Embedding generation completed without persisted embeddings`, spusť
  `gitnexus analyze --force` a zapiš výsledek. Zapiš celý řádek FTS z `doctor`.

**T10 — FTS bez OpenSSL z Git for Windows**
- Cíl: 4.5 (S5), preflight kontrola OpenSSL v 6.4.
- Kroky:
  ```powershell
  $env:Path = ($env:Path -split ';' | Where-Object { $_ -notlike '*\Git\mingw64\bin*' }) -join ';'
  where.exe libssl-3-x64.dll
  Set-Location "$W\proj-a"
  gitnexus analyze --force 2>&1 | Select-Object -Last 15
  gitnexus doctor
  ```
  Pak znovu s `C:\Program Files\Git\mingw64\bin` na začátku PATH a s
  `gitnexus analyze --repair-fts`.
- Vyhodnocení: `PASS`, když se potvrdí chování z S5 (bez DLL FTS selže, s DLL a
  `--repair-fts` funguje). Jinak zapiš skutečné chování.

#### D. Ollama, qdrant a grepai

**T11 — Ollama a embedding model**
- Cíl: 4.3, bod 6 kapitoly 11.
- Kroky:
  ```powershell
  Get-Process *ollama* -ErrorAction SilentlyContinue | Select-Object Name, Id, Path
  Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' | Format-List
  ollama list
  ollama pull nomic-embed-text-v2-moe
  Invoke-RestMethod -Method Post http://localhost:11434/api/embed -Body '{"model":"nomic-embed-text-v2-moe","input":"hello"}' -ContentType 'application/json' | ForEach-Object { $_.embeddings[0].Count }
  ```
- Vyhodnocení: `PASS`, když embedding vrátí nenulový počet dimenzí. Zapiš názvy
  a cesty procesů Ollama a záznam v `Run`, pokud existuje.

**T12 — grepai**
- Cíl: 4.6.
- Kroky (instalace v samostatném skriptu, kontrola v dalším kvůli PATH):
  ```powershell
  irm https://raw.githubusercontent.com/yoanbernabeu/grepai/main/install.ps1 | iex
  ```
  ```powershell
  Get-Command grepai | Select-Object Source
  grepai version
  ```
- Vyhodnocení: `PASS`, když `grepai version` vypíše verzi.

**T13 — stažení a ověření `qdrant.exe` (Q15)**
- Cíl: 6.12 (instalace), S27.
- Kroky, varianta PowerShell (referenční):
  ```powershell
  foreach ($v in '1.18.3','1.19.1') {
    $rel = Invoke-RestMethod "https://api.github.com/repos/qdrant/qdrant/releases/tags/v$v"
    $a = $rel.assets | Where-Object name -eq 'qdrant-x86_64-pc-windows-msvc.zip'
    "v$v digest: $($a.digest)"
    Invoke-WebRequest $a.browser_download_url -OutFile "$W\qdrant-$v.zip"
    "v$v local:  sha256:$((Get-FileHash "$W\qdrant-$v.zip" -Algorithm SHA256).Hash.ToLower())"
  }
  ```
  Varianta Python (mechanismus navržený pro `--install-deps`). Soubor
  `$W\scripts\t13_fetch.py`:
  ```python
  import hashlib, json, pathlib, shutil, sys, tempfile, urllib.request, zipfile
  version, dest = sys.argv[1], pathlib.Path(sys.argv[2])
  api = "https://api.github.com/repos/qdrant/qdrant/releases/tags/v" + version
  rel = json.load(urllib.request.urlopen(api, timeout=30))
  asset = next(a for a in rel["assets"] if a["name"] == "qdrant-x86_64-pc-windows-msvc.zip")
  with tempfile.TemporaryDirectory() as tmp:
      zpath = pathlib.Path(tmp) / asset["name"]
      with urllib.request.urlopen(asset["browser_download_url"], timeout=300) as r, open(zpath, "wb") as f:
          shutil.copyfileobj(r, f)
      digest = "sha256:" + hashlib.sha256(zpath.read_bytes()).hexdigest()
      print("expected", asset["digest"], "actual", digest, "match", digest == asset["digest"])
      if digest != asset["digest"]:
          sys.exit(1)
      out = dest / version
      out.mkdir(parents=True, exist_ok=True)
      zipfile.ZipFile(zpath).extractall(out)
      print("extracted", [p.name for p in out.iterdir()])
  ```
  ```powershell
  python "$W\scripts\t13_fetch.py" 1.18.3 "$W\qdrant\bin"
  python "$W\scripts\t13_fetch.py" 1.19.1 "$W\qdrant\bin"
  Get-ChildItem -Recurse "$W\qdrant\bin" -Filter qdrant.exe | Select-Object FullName, Length
  ```
- Vyhodnocení: `PASS`, když obě varianty mají shodný SHA-256 s digestem z API
  a `qdrant.exe` je rozbalený. Zapiš strukturu zipu (je `qdrant.exe` přímo
  v kořeni?). Zapiš, jestli `urllib` narazil na proxy nebo certifikáty.

**T14 — spuštění nativního qdrant a firewall**
- Cíl: 6.12 (spuštění), body 11 a 12 kapitoly 11, S27.
- Soubor `$W\scripts\qdrant_start.py`:
  ```python
  import os, pathlib, subprocess, sys
  base, exe = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
  host = sys.argv[3] if len(sys.argv) > 3 else "127.0.0.1"
  base.mkdir(parents=True, exist_ok=True)
  env = dict(os.environ)
  env.update({
      "QDRANT__SERVICE__HOST": host,
      "QDRANT__SERVICE__HTTP_PORT": "6333",
      "QDRANT__SERVICE__GRPC_PORT": "6334",
      "QDRANT__STORAGE__STORAGE_PATH": str(base / "storage"),
      "QDRANT__STORAGE__SNAPSHOTS_PATH": str(base / "snapshots"),
      "QDRANT__TELEMETRY_DISABLED": "true",
  })
  log = open(base / "qdrant.log", "ab")
  p = subprocess.Popen([str(exe)], cwd=str(base), env=env, stdin=subprocess.DEVNULL,
                       stdout=log, stderr=subprocess.STDOUT,
                       creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
  (base / "qdrant.pid").write_text(str(p.pid))
  print("pid", p.pid)
  ```
  Kroky:
  ```powershell
  $exe = (Get-ChildItem -Recurse "$W\qdrant\bin\1.19.1" -Filter qdrant.exe | Select-Object -First 1).FullName
  & $exe --version
  python "$W\scripts\qdrant_start.py" "$W\qdrant\data" $exe 127.0.0.1
  Start-Sleep 10
  Invoke-WebRequest http://127.0.0.1:6333/healthz -UseBasicParsing | Select-Object StatusCode, Content
  Invoke-RestMethod http://127.0.0.1:6333/ | ConvertTo-Json
  Test-NetConnection 127.0.0.1 -Port 6334 | Select-Object TcpTestSucceeded
  Get-NetTCPConnection -LocalPort 6333,6334 -State Listen | Select-Object LocalAddress, LocalPort, OwningProcess
  Get-ChildItem "$W\qdrant\data" | Select-Object Name
  Get-Content "$W\qdrant\data\qdrant.log" -Tail 30
  ```
  **[člověk]** Zeptej se, jestli se objevil dialog Windows Defender Firewall.

  Potom qdrant zastav (`Stop-Process -Id (Get-Content "$W\qdrant\data\qdrant.pid")`),
  spusť ho znovu s třetím argumentem `0.0.0.0` a znovu se zeptej na dialog.
  Nakonec ho zastav a spusť znovu s `127.0.0.1`; ten běh nech pro další testy.
- Vyhodnocení: `PASS`, když `healthz` vrátí 200, port 6334 je otevřený,
  naslouchá se jen na `127.0.0.1` a `storage` vznikl v `$W\qdrant\data`.
  Zapiš výstup `--version` a `GET /` (obsahuje verzi?), hlášení kontroly
  souborového systému v logu a oba výsledky dialogu firewallu.

**T15 — grepai proti nativnímu qdrant**
- Cíl: 6.12 (architektura), N9 (formát cest), parsery v `integrations.py`
  (`mapped_path`, `watcher_running`), 6.9 (logy).
- Kroky (argumenty odpovídají tomu, co produkt volá v `commands.py:937–972`):
  ```powershell
  Set-Location "$W\proj-a"
  grepai workspace create aci-phase0 --backend qdrant --qdrant-endpoint http://127.0.0.1 --qdrant-port 6334 --provider ollama --model nomic-embed-text-v2-moe --yes
  grepai workspace show aci-phase0
  grepai workspace add aci-phase0 "$W\proj-a"
  grepai workspace show aci-phase0
  grepai init --yes -p ollama -b qdrant -m nomic-embed-text-v2-moe
  Get-Content .grepai\config.yaml
  grepai watch --workspace aci-phase0 --background
  grepai watch --workspace aci-phase0 --status
  Start-Sleep 90
  (Invoke-RestMethod http://127.0.0.1:6333/collections/workspace_aci-phase0).result | Select-Object status, points_count
  grepai search "verifying a user password" --workspace aci-phase0
  grepai search --workspace aci-phase0 --json -n 5 -- "verifying a user password"
  Get-ChildItem "$env:LOCALAPPDATA\grepai\logs"
  ```
  Pak ověř velikost písmen v cestě:
  ```powershell
  grepai workspace add aci-phase0 "$W\PROJ-A"
  grepai workspace show aci-phase0
  grepai watch --workspace aci-phase0 --stop
  grepai watch --workspace aci-phase0 --status
  ```
- Vyhodnocení: `PASS`, když `points_count` > 0 a hledání najde `src\app.js`.
  Doslovně zapiš: výstup `workspace show` (formát cesty, lomítka, velikost
  písmen), výstup `watch --status` při běhu i po zastavení, název souboru logu
  a chování druhého `workspace add` s jinou velikostí písmen.

**T16 — upgrade dat qdrant o jednu minor verzi**
- Cíl: 6.12 (verze), S28, R11.
- Kroky:
  ```powershell
  Stop-Process -Id (Get-Content "$W\qdrant\data\qdrant.pid") -ErrorAction SilentlyContinue
  $old = (Get-ChildItem -Recurse "$W\qdrant\bin\1.18.3" -Filter qdrant.exe | Select-Object -First 1).FullName
  $new = (Get-ChildItem -Recurse "$W\qdrant\bin\1.19.1" -Filter qdrant.exe | Select-Object -First 1).FullName
  python "$W\scripts\qdrant_start.py" "$W\qdrant\upgrade" $old 127.0.0.1
  Start-Sleep 10
  Invoke-RestMethod -Method Put http://127.0.0.1:6333/collections/upgrade_test -Body '{"vectors":{"size":4,"distance":"Cosine"}}' -ContentType 'application/json'
  Invoke-RestMethod -Method Put "http://127.0.0.1:6333/collections/upgrade_test/points?wait=true" -Body '{"points":[{"id":1,"vector":[0.1,0.2,0.3,0.4]}]}' -ContentType 'application/json'
  Invoke-RestMethod http://127.0.0.1:6333/ | ConvertTo-Json
  Stop-Process -Id (Get-Content "$W\qdrant\upgrade\qdrant.pid")
  Start-Sleep 3
  python "$W\scripts\qdrant_start.py" "$W\qdrant\upgrade" $new 127.0.0.1
  Start-Sleep 10
  Invoke-RestMethod http://127.0.0.1:6333/ | ConvertTo-Json
  (Invoke-RestMethod http://127.0.0.1:6333/collections/upgrade_test).result | Select-Object status, points_count
  Get-Content "$W\qdrant\upgrade\qdrant.log" -Tail 20
  Stop-Process -Id (Get-Content "$W\qdrant\upgrade\qdrant.pid")
  python "$W\scripts\qdrant_start.py" "$W\qdrant\data" $new 127.0.0.1
  ```
- Vyhodnocení: `PASS`, když po upgradu na 1.19.1 kolekce existuje s
  `points_count` = 1. Zapiš, jak zjistit verzi dat na disku (soubory ve
  `storage`, hlášení v logu).

**T17 — Windows Defender a výkon**
- Cíl: R7, R13, bod 14 kapitoly 11. Informativní.
- Kroky:
  ```powershell
  Get-MpComputerStatus | Select-Object RealTimeProtectionEnabled, AMRunningMode
  Set-Location "$W\proj-a"
  (Measure-Command { gitnexus analyze --force | Out-Null }).TotalSeconds
  ```
- Vyhodnocení: `PASS` s čísly; `BLOCKED`, když `Get-MpComputerStatus` vyžaduje
  administrátora.

#### E. Agenti

**T18 — Claude Code: instalace a Bash tool**
- Cíl: 4.8, S14.
- Kroky: `claude --version; claude doctor` a `where.exe claude`.
- Vyhodnocení: `PASS`, když `claude doctor` nehlásí chybu a najde Git Bash.

**T19 — Claude Code: SessionStart hook v exec form (Q12)**
- Cíl: 6.5, S15, N12.
- Kroky: v `$W\proj-a` vytvoř `.claude\helpers\code-context-hint.mjs`:
  ```javascript
  import { appendFileSync } from 'node:fs';
  import { join } from 'node:path';
  const dir = process.env.CLAUDE_PROJECT_DIR || process.cwd();
  appendFileSync(join(dir, '.claude', 'hook-ran.txt'), `${new Date().toISOString()} exec-form ${process.platform}\n`);
  console.log(JSON.stringify({ hookSpecificOutput: { hookEventName: 'SessionStart', additionalContext: 'ACI_PHASE0_HINT_MARKER_EXEC' } }));
  ```
  a `.claude\settings.json`:
  ```json
  {
    "hooks": {
      "SessionStart": [
        { "hooks": [ { "type": "command", "command": "node", "args": ["${CLAUDE_PROJECT_DIR}/.claude/helpers/code-context-hint.mjs"], "timeout": 5000 } ] }
      ]
    }
  }
  ```
  Spusť v `$W\proj-a`:
  ```powershell
  claude -p "If your context contains a string starting with ACI_PHASE0_HINT_MARKER, reply with that exact string. Otherwise reply NONE."
  Get-Content "$W\proj-a\.claude\hook-ran.txt"
  ```
  Když `-p` hook nespustí, požádej **[člověk]** o spuštění interaktivního
  `claude` v `$W\proj-a` (potvrdit důvěru v projekt), položení stejné otázky a
  ukončení. Pak zkontroluj `hook-ran.txt`.

  Druhý běh s dnešním tvarem produktu (shell form, Python). Vytvoř
  `.claude\helpers\hint-legacy.py`:
  ```python
  import datetime, json, os, pathlib
  d = pathlib.Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))
  with open(d / ".claude" / "hook-ran.txt", "a") as f:
      f.write("%s shell-form-python\n" % datetime.datetime.now().isoformat())
  print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                    "additionalContext": "ACI_PHASE0_HINT_MARKER_LEGACY"}}))
  ```
  V `settings.json` nahraď hook tímto a zopakuj `claude -p` se stejnou otázkou:
  ```json
  { "type": "command", "command": "python3 \"${CLAUDE_PROJECT_DIR:-.}/.claude/helpers/hint-legacy.py\"", "timeout": 5000 }
  ```
- Vyhodnocení: `PASS`, když exec form zapíše řádek a agent vrátí
  `ACI_PHASE0_HINT_MARKER_EXEC`. Výsledek dnešního tvaru zapiš jako fakt
  (očekává se problém s `python3`; potvrzuje N12).

**T20 — Claude Code: oprávnění pro PowerShell tool (Q6)**
- Cíl: 6.1 (oprávnění), bod 16 kapitoly 11, S32.
- Kroky: vytvoř falešný příkaz `$W\fakebin\agent-code-intel.cmd`:
  ```bat
  @echo off
  echo %DATE% %TIME% %* >> "%USERPROFILE%\aci-phase0\t20-ran.txt"
  echo ACI_PHASE0_REFRESH_RAN
  ```
  V `$W\proj-perm` (nový adresář, `git init`) vytvoř `.claude\settings.json`
  pro každý běh zvlášť a spusť `claude` s `$W\fakebin` na začátku PATH:
  ```powershell
  $env:Path = "$W\fakebin;$env:Path"
  Set-Location "$W\proj-perm"
  claude -p "Use the PowerShell tool (not Bash) to run exactly: agent-code-intel --refresh . Then report the output."
  ```
  | Běh | `permissions.allow` | Tool v promptu |
  | --- | --- | --- |
  | a | `["Bash(agent-code-intel --refresh)"]` | PowerShell |
  | b | `["Bash(agent-code-intel --refresh)", "PowerShell(agent-code-intel --refresh)"]` | PowerShell |
  | c | stejné jako b | Bash |

  Prompt a přesný text příkazu v promptu drž stejný jako produkt:
  `agent-code-intel --refresh`. Po každém běhu zapiš, jestli přibyl řádek
  v `t20-ran.txt` a co agent odpověděl (spustil / odmítnut kvůli oprávnění).
- Vyhodnocení: `PASS`, když běh b a c příkaz spustí bez dotazu. Běh a slouží
  jako kontrola, že bez pravidla PowerShell se příkaz nespustí. Když agent
  PowerShell tool nemá, zapiš to a označ `PARTIAL`.

**T21 — Claude Code: MCP servery**
- Cíl: 6.6, N13, S5.
- Kroky (scope `local`, aby se neměnila uživatelská konfigurace):
  ```powershell
  Set-Location "$W\proj-a"
  claude mcp add aci-phase0-gitnexus-cmd -s local -- cmd /c gitnexus mcp
  claude mcp add aci-phase0-gitnexus-bare -s local -- gitnexus mcp
  claude mcp add aci-phase0-grepai -s local -- grepai mcp-serve --workspace aci-phase0
  claude mcp list
  ```
  Pak všechny tři odeber (`claude mcp remove <name> -s local`).
- Vyhodnocení: `PASS`, když `-cmd` a `grepai` jsou připojené. Zapiš stav
  `-bare` (očekává se selhání; potvrzuje N13).

**T22 — Codex: instalace a typ spustitelného souboru**
- Cíl: 6.6 (`codex` jako `.cmd`?), 4.8.
- Kroky: `where.exe codex; codex --version`. **[člověk]** přihlášení, pokud
  je potřeba.
- Vyhodnocení: `PASS`, když `codex --version` odpovídá. Zapiš příponu
  nalezeného souboru.

**T23 — Codex: MCP gitnexus**
- Cíl: 6.6.
- Kroky:
  ```powershell
  codex mcp add aci-phase0-gitnexus -- cmd /c gitnexus mcp
  codex mcp get aci-phase0-gitnexus
  codex mcp list
  Set-Location "$W\proj-a"
  codex exec "List the tools exposed by the MCP server named aci-phase0-gitnexus. If it is unavailable, say MCP_UNAVAILABLE and quote the error."
  codex mcp remove aci-phase0-gitnexus
  ```
- Vyhodnocení: `PASS`, když `codex exec` vypíše nástroje GitNexus.

**T24 — Codex: shell hooku a relativní cesta (Q3)**
- Cíl: 6.5 (Codex), S31, bod 2 kapitoly 11, R3.
- Kroky, běh 1 (který shell). V `$W\proj-a\.codex\hooks.json`:
  ```json
  {
    "hooks": {
      "SessionStart": [
        { "hooks": [ { "type": "command", "command": "echo posix > .codex-shell.txt", "commandWindows": "echo %COMSPEC%> .codex-shell.txt", "timeout": 5 } ] }
      ]
    }
  }
  ```
  **[člověk]** v `$W\proj-a` spustí `codex`, potvrdí důvěru v projekt, přes
  `/hooks` schválí hook, pošle zprávu „hi“ a ukončí Codex. Ověř, že
  `~/.codex/config.toml` neobsahuje `[features]` s `hooks = false`.
  ```powershell
  Get-Content "$W\proj-a\.codex-shell.txt"
  ```
  Obsah rozhoduje: rozvinutá cesta (např. `C:\Windows\system32\cmd.exe`) =
  `cmd.exe`; doslovné `%COMSPEC%` = PowerShell; soubor chybí = hook neběžel.

  Běh 2 (relativní cesta). Nahraď hook tímto a znovu nech schválit:
  ```json
  { "type": "command", "command": "node \"$(git rev-parse --show-toplevel)/.claude/helpers/code-context-hint.mjs\"", "commandWindows": "node .claude/helpers/code-context-hint.mjs", "timeout": 5 }
  ```
  Skript z T19 zapisuje do `hook-ran.txt` (použije `process.cwd()`, protože
  Codex nenastavuje `CLAUDE_PROJECT_DIR`). **[člověk]** spustí `codex`
  jednou v `$W\proj-a` a jednou v `$W\proj-a\src\sub`, pokaždé pošle „hi“.
  Zkontroluj `hook-ran.txt` a zapiš, jak Codex ohlásil chybu v podadresáři.
- Vyhodnocení: `PASS`, když běh 1 určí shell a běh 2 z kořene zapíše řádek.
  Selhání z podadresáře je očekávané (R3); zapiš jeho projev.

#### F. Dnešní stav agent-code-intel na Windows

**T25 — CLI z checkoutu**
- Cíl: základní linie pro N1–N24, sekce 3.1.
- Kroky (vlastní konfigurace a domov, aby se nesahalo na uživatele):
  ```powershell
  $env:XDG_CONFIG_HOME = "$W\xdg"
  $env:HOME = "$W\home"
  New-Item -ItemType Directory -Force "$W\xdg","$W\home","$W\proj-b" | Out-Null
  Set-Location $R
  python .\agent-code-intel --version
  python .\agent-code-intel --help | Select-Object -First 20
  python .\agent-code-intel --install-deps --no-install-deps
  "exit: $LASTEXITCODE"
  python .\agent-code-intel --status --json --path "$W\proj-a"
  python .\agent-code-intel --agent claude --path "$W\proj-b" --no-bootstrap
  "exit: $LASTEXITCODE"
  ```
- Vyhodnocení: vždy `PASS` se záznamem. U každé chyby nebo podezřelého řádku
  uveď, který nález N z kapitoly 5 potvrzuje, nebo že jde o nový nález (N25+).

**T26 — `--install` do dočasného domova**
- Cíl: N1, N2, N20, 6.1.
- Kroky:
  ```powershell
  $env:XDG_CONFIG_HOME = "$W\xdg"
  $env:HOME = "$W\home"
  Set-Location $R
  python .\agent-code-intel --install --no-perms
  "exit: $LASTEXITCODE"
  Get-ChildItem -Recurse "$W\home\.local" -Depth 2 | Select-Object FullName
  Get-Content "$W\home\.local\bin\agent-code-intel" -TotalCount 3
  & "$W\home\.local\bin\agent-code-intel" --version
  python "$W\home\.local\bin\agent-code-intel" --version
  Get-ChildItem -Recurse "$env:USERPROFILE\.local" -ErrorAction SilentlyContinue | Select-Object -First 5 FullName
  ```
- Vyhodnocení: vždy `PASS` se záznamem. Zapiš, kam instalace skutečně psala
  (respektovala `HOME`?), co udělalo přímé spuštění souboru bez přípony a jestli
  něco vzniklo mimo `$W`.

**T27 — unit testy**
- Cíl: 6.10, základní linie.
- Kroky:
  ```powershell
  Set-Location "$R\test\unit"
  python -m unittest discover -s . -t . 2>&1 | Select-Object -Last 60
  ```
- Vyhodnocení: vždy `PASS` se záznamem: počet testů, počet selhání a chyb a
  seznam selhaných testů s první řádkou chyby.

#### G. Ostatní

**T28 — nástroje code-context**
- Cíl: 4.7, 6.4, body 4, 5 a 9 kapitoly 11.
- Kroky:
  ```powershell
  winget install --id sharkdp.fd --id BurntSushi.ripgrep.MSVC -e --accept-source-agreements --accept-package-agreements
  "multi-id exit: $LASTEXITCODE"
  ```
  Když příkaz s více id selže, nainstaluj je po jednom. Pak:
  ```powershell
  winget install --id UniversalCtags.Ctags -e --accept-source-agreements --accept-package-agreements
  winget install --id ast-grep.ast-grep -e --accept-source-agreements --accept-package-agreements
  winget search scc
  winget search tokei
  winget search ripgrep-all
  ```
  ```powershell
  rg --version; fd --version; ctags --version; ast-grep --version
  Set-Location $R
  ctags -x --_xformat='%N L%n-%{end} %K' -o - agent_code_intel\project.py | rg '^canon '
  ```
  A totéž v Git Bash:
  ```
  cd "$USERPROFILE/src/agent-code-intel" && TMPDIR=. ctags -x --_xformat='%N L%n-%{end} %K' -o - agent_code_intel/project.py | rg '^canon '
  ```
- Vyhodnocení: `PASS`, když `rg`, `fd`, `ctags` (Universal) a `ast-grep`
  fungují a oba příkazy `ctags` vrátí `canon L101-121 function`. Zapiš, jestli
  winget přijal více id a co našel pro `scc`, `tokei` a `ripgrep-all`.

**T29 — výpis procesů přes CIM**
- Cíl: 6.9, bod 7 kapitoly 11.
- Soubor `$W\scripts\t29_cim.py`:
  ```python
  import json, subprocess, time
  cmd = ("Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,CreationDate,CommandLine "
         "| ConvertTo-Json -Compress")
  t0 = time.monotonic()
  p = subprocess.run(["powershell.exe", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=60)
  rows = json.loads(p.stdout)
  print("seconds", round(time.monotonic() - t0, 2), "rows", len(rows))
  print("sample", json.dumps(rows[0])[:400])
  print("node rows", [r for r in rows if r.get("CommandLine") and "node" in r["CommandLine"].lower()][:3])
  ```
- Vyhodnocení: `PASS`, když JSON jde načíst. Doslovně zapiš formát
  `CreationDate` a dobu běhu.

#### H. Odhlášení a restart (nakonec)

Před H2 a H3 ulož soubor výsledků. Po návratu začni čtením 15.1 a souboru
výsledků.

**H1 — zavření konzole křížkem**
- Cíl: 6.2 (proces bez `DETACHED_PROCESS`).
- Kroky: ulož `$W\scripts\sleeper.py` s obsahem
  `import time; time.sleep(3600)` a spusť
  `Start-Process powershell.exe -ArgumentList '-NoExit','-File',"`"$W\scripts\h1.ps1`""`,
  kde `h1.ps1` obsahuje `python "$env:USERPROFILE\aci-phase0\scripts\sleeper.py"`.
  Zapiš PID pythonu
  (`Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Select-Object ProcessId, CommandLine`).
  **[člověk]** zavře okno křížkem. Ověř, jestli proces běží.
- Vyhodnocení: vždy `PASS` se záznamem.

**H2 — odhlášení a automatický start (Q16)**
- Cíl: 6.12 (Kdy se qdrant spouští), body 10 a 13 kapitoly 11.
- Příprava:
  - Soubor `$W\scripts\qdrant_autostart.pyw` spustí qdrant jen, když
    `http://127.0.0.1:6333/healthz` neodpovídá:
    ```python
    import pathlib, subprocess, sys, urllib.request
    W = pathlib.Path.home() / "aci-phase0"
    try:
        urllib.request.urlopen("http://127.0.0.1:6333/healthz", timeout=2)
        (W / "autostart.txt").open("a").write("already running\n")
        sys.exit(0)
    except Exception:
        pass
    exe = next((W / "qdrant" / "bin" / "1.19.1").rglob("qdrant.exe"))
    subprocess.run([sys.executable, str(W / "scripts" / "qdrant_start.py"), str(W / "qdrant" / "data"), str(exe), "127.0.0.1"])
    (W / "autostart.txt").open("a").write("started\n")
    ```
  - Zástupce ve složce Po spuštění (bez administrátora):
    ```powershell
    $startup = [Environment]::GetFolderPath('Startup')
    $pyw = (Get-Command pythonw).Source
    $lnk = (New-Object -ComObject WScript.Shell).CreateShortcut("$startup\aci-phase0-qdrant.lnk")
    $lnk.TargetPath = $pyw
    $lnk.Arguments = "`"$W\scripts\qdrant_autostart.pyw`""
    $lnk.WorkingDirectory = $W
    $lnk.Save()
    Get-Item "$startup\aci-phase0-qdrant.lnk"
    ```
  - Úloha v Plánovači úloh (pouze pokus o registraci bez administrátora):
    ```powershell
    $action = New-ScheduledTaskAction -Execute (Get-Command pythonw).Source -Argument "`"$W\scripts\qdrant_autostart.pyw`""
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
    Register-ScheduledTask -TaskName 'aci-phase0-qdrant-task' -Action $action -Trigger $trigger
    "exit: $?"
    ```
    Když registrace projde, úlohu hned vypni
    (`Disable-ScheduledTask -TaskName 'aci-phase0-qdrant-task'`), aby se oba
    mechanismy nepletly. Zapiš jen, zda registrace bez administrátora prošla.
  - Zapiš PID procesu z T05 a PID qdrant.
- **[člověk]** se odhlásí a znovu přihlásí. Hlídá, jestli se po přihlášení
  objevilo nějaké okno konzole, a řekne to agentovi.
- Po návratu:
  ```powershell
  Get-Process -Id (Get-Content "$W\t05.pid") -ErrorAction SilentlyContinue
  Get-Content "$W\autostart.txt" -ErrorAction SilentlyContinue
  Invoke-WebRequest http://127.0.0.1:6333/healthz -UseBasicParsing | Select-Object StatusCode
  Get-Process qdrant -ErrorAction SilentlyContinue | Select-Object Id, StartTime
  ollama list
  ```
- Vyhodnocení: `PASS`, když qdrant po přihlášení běží díky zástupci, bez
  viditelného okna a bez administrátora. Zapiš, jestli proces z T05 a původní
  qdrant odhlášení přežily.

**H3 — restart Windows**
- Cíl: R12, 4.3 (Ollama po restartu), 6.12.
- **[člověk]** restartuje Windows a přihlásí se.
- Po návratu stejné kontroly jako v H2 plus `grepai watch --workspace aci-phase0 --status`.
- Vyhodnocení: `PASS`, když qdrant a Ollama po restartu běží bez zásahu.
  Stav watcheru grepai zapiš (očekává se, že neběží, jako na macOS).

### 15.6 Úklid

Po zapsání všech výsledků, se souhlasem člověka:

```powershell
Get-Process qdrant -ErrorAction SilentlyContinue | Stop-Process
Remove-Item "$([Environment]::GetFolderPath('Startup'))\aci-phase0-qdrant.lnk" -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName 'aci-phase0-qdrant-task' -Confirm:$false -ErrorAction SilentlyContinue
grepai watch --workspace aci-phase0 --stop
grepai workspace delete aci-phase0
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*time.sleep(3600)*' -or $_.CommandLine -like '*sleeper.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId }
```

`grepai workspace delete <name>` existuje ve zdrojích grepai (`cli/workspace.go`). Adresář `$W`
nemaž; člověk rozhodne. Nainstalované nástroje nech.

### 15.7 Verdikt

Na konci souboru výsledků vyplň tuto tabulku. Oblast je **GO**, když všechny
její povinné testy mají `PASS`. **NO-GO** znamená, že plán v dané oblasti
nejde implementovat, jak je navržen; uveď proč a navrhni alternativu.

| Oblast | Povinné testy | Doplňkové testy | Verdikt |
| --- | --- | --- | --- |
| Instalace základu | T00, T01, T02 | T03 | |
| Spouštění nástrojů z Pythonu | T04, T05 | T06, T07, H1 | |
| GitNexus | T09 | T10, T17 | |
| Nativní qdrant | T13, T14, T16 | H2 (qdrant přežil) | |
| grepai + Ollama | T11, T12, T15 | | |
| Automatický start (Q16) | H2 | H3 | |
| Claude Code | T18, T19, T21 | T20 | |
| Codex | T22, T23 | T24 | |
| Code-context nástroje | T28 | | |
| Dashboard (procesy) | T29 | | |
| Dnešní stav produktu | T25, T26, T27 | | |

**Celkový verdikt:** GO, když jsou všechny oblasti GO, nebo když NO-GO je jen
v doplňkových testech. Jinak NO-GO s výčtem blokujících oblastí.

**Hotovo, když:** každý test T00–T29 a H1–H3 má stav, každý `BLOCKED` má důvod,
tabulka verdiktu je vyplněná a sekce „Navržené úpravy windows-support.md“
pokrývá všechny body kapitoly 11.
