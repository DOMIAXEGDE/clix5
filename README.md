# CLI Scripted Kernel — Extreme C++23 File-Backed Workflow

A fast, minimal, **file-backed** C++23 CLI for structured “banks” of registers/addresses, with a **pluggable code-plugin system**. Everything flows through plain **`.txt`** and **`.json`** files so you can version, diff, test, and automate without opaque binaries.

---

## Highlights

* **C++23 single-binary CLI** (`cli-script.exe`)
* **Deterministic file format** for contexts/banks
* **Resolver** supports references across banks/registers
* **Plugins**: language-agnostic, file-based (`run.bat`/`run.sh`)
* **Artifacts**: resolved text + JSON exports under `files/out/`
* **Batteries**: PowerShell build (`build.ps1`), wrapper, smoke tests

---

## Repository Layout

```
.
├─ build.ps1                    # Build/stage helper (PS 5.1+)
├─ clix.cmd                     # Wrapper: launches CLI in bin\
├─ scripted.cpp                 # main (Windows entrypoint uses this)
├─ scripted_core.hpp            # core data model + parser/resolver
├─ scripted_kernel.hpp          # code-plugin kernel (no scripted_exec.hpp)
├─ plugins\                     # source plugins (staged to bin\plugins\)
│  └─ python\
│     ├─ plugin.json            # { name, entry_win, entry_lin }
│     ├─ run.bat                # Windows entry (args: %1=input.json %2=outdir)
│     └─ run.sh                 # POSIX entry  (args: $1, $2)
├─ files\                       # source contexts (staged to bin\files\)
│  └─ out\                      # resolved + exports (under bin\files\out\)
├─ bin\                         # build output + staged files/plugins
│  ├─ cli-script.exe
│  ├─ files\                    # working contexts (at runtime)
│  └─ plugins\                  # working plugins (at runtime)
├─ smoke.ps1                    # resolver smoke test
└─ plugin-smoke.ps1             # plugin pipeline smoke test
```

---

## Requirements (Windows)

* **PowerShell 5.1+**
* **MinGW g++ (via Chocolatey)**: `choco install mingw -y`
* Optional: Visual Studio 2022 (if you prefer an IDE) — this project also builds fine there as a C++ Console App.

> If PowerShell blocks scripts:
> `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser -Force`

---

## Build & Run

### Quick build (Release)

```powershell
cd D:\domalecs-os\clix5
.\build.ps1 -Release
```

Artifacts land in `.\bin\` (and the script stages `files\` and `plugins\` into `bin\`).

### Run the CLI

```powershell
# Easiest: use the wrapper so working dir is bin\
clix
# or directly:
cd .\bin
.\cli-script.exe
```

Add the repo root to your **User PATH** to run `clix` from anywhere:

```powershell
$repo = 'D:\domalecs-os\clix5'
$cur  = [Environment]::GetEnvironmentVariable('Path','User')
if ($cur -notlike "*$repo*") {
  [Environment]::SetEnvironmentVariable('Path', $cur.TrimEnd(';') + ';' + $repo, 'User')
}
```

### Build options (PowerShell)

* `.\build.ps1 -Release` — optimized (`-O2 -DNDEBUG -s`)
* `.\build.ps1 -Run` — build **and** run CLI
* `.\build.ps1 -Clean` — remove `bin\`
* `.\build.ps1 -Std c++20` — change standard (default: `c++23`)
* `.\build.ps1 -Static:$false` — disable static libstdc++/libgcc in Release

> Target: **g++ 13.x** or newer with **-std=c++23** (default).

---

## Concepts

### Context (“Bank”)

Each context lives in `files/<ctx>.txt`. The **stem** is the context id (e.g. `x00001`), where `x` is the **prefix**, and the rest is base-N (default base-10) number with fixed widths.

**Bank file format (deterministic)**

```
x00001  (demo context){
01
        0001    print("hello")
02
        0000    x00001.01.0001
}
```

* **Header**: `<ctx>  (<title>){`
* Body is **register blocks**:

  * `01` — register id (no indentation)
  * under it, **address lines** (indented by **TAB or SPACE**), `addr` then value
* **Trailer**: `}` on its own line

**Notes**

* UTF-8 BOM is supported (automatically stripped).
* Tabs or spaces are accepted for indentation.
* Widths/base are configurable (see `:set widths`, `:set base`).

### Addressing & Resolution

Resolver expands references in values. Supported forms:

* **`@file(name.txt)`** — inline include from `files/name.txt`
* **Prefixed 3-part**: `x<bank>.<reg>.<addr>`
  Example: `x00001.01.0001`
* **Same-bank shorthand**: `r<reg>.<addr>`
  Uses current bank: `r02.0000`
* **Prefixed 2-part** (reg **01** by default): `x<bank>.<addr>`
  Example: `x00001.0001` == `x00001.01.0001`
* **Numeric triad**: `<bank>.<reg>.<addr>`
  Example: `00001.01.0001`

**Order of passes**: `@file` ➜ `x.b.r.a` ➜ `r.r.a` ➜ `x.b.a` ➜ `b.r.a`
(Circular references are detected and flagged; missing cells are flagged.)

**Artifacts**

* `files/out/<ctx>.resolved.txt` — resolved snapshot (`:resolve`)
* `files/out/<ctx>.json` — full structured export (`:export`)

---

## CLI Commands

Type `:help` inside the CLI to see the list. Key commands:

```
:open <ctx>          # open/create context (e.g., x00001 or x00001.txt)
:switch <ctx>        # switch current context
:preload             # load all banks from files/
:ls                  # list loaded contexts
:show                # print current buffer
:ins <addr> <value>  # insert/replace in register 01
:insr <reg> <addr> <value>
:del <addr>          # delete in register 01
:delr <reg> <addr>   # delete in specific register
:w                   # write current buffer to files/<ctx>.txt
:r <path>            # read/merge a raw snippet from file
:resolve             # write files/out/<ctx>.resolved.txt
:export              # write files/out/<ctx>.json
:set prefix <char>   # e.g., x
:set base <n>        # e.g., 10 or 16
:set widths bank=5 addr=4 reg=2
:plugins             # list discovered code plugins
:plugin_run <name> <reg> <addr> [stdin.json|inlineJSON]
:q                   # quit
```

### Examples

```text
:open x00001
:ins 0001 print("hello")
:insr 02 0000 x00001.01.0001
:w
:resolve
:export
```

To import a resolved snapshot back into memory:

```text
:r files/out/x00001.resolved.txt
:show
```

---

## Plugins (file-based, language-agnostic)

**Discovery**
`plugins/*/plugin.json`:

```json
{ "name": "<pluginName>", "entry_win": "run.bat", "entry_lin": "run.sh" }
```

Shown by `:plugins` (prints name and path).

**Invocation**

```
:plugin_run <name> <reg> <addr> [stdin.json | inlineJSON]
```

* Use `{}` for no stdin.
* For inline JSON with spaces, prefer a file: `:plugin_run python 01 0001 files\stdin.json`
* **Don’t** type the square brackets literally; they mean “optional”.

**What the Kernel writes per run**
`files/out/plugins/<ctx>/r<reg>a<addr>/<plugin>/`

* `code.txt` — resolved cell value
* `input.json` — metadata + optional stdin object
* `output.json` — **REQUIRED** result (plugin writes this)
* `run.log` / `run.err` — captured stdout/stderr
* `run.cmd` — Windows breadcrumb (exact command executed)

**Entry script arguments (absolute paths)**

* **Windows (`run.bat`)**: `%1 = input.json`, `%2 = outdir`
* **POSIX (`run.sh`)**: `$1 = input.json`, `$2 = outdir`

**Example Windows plugin (`plugins\python\run.bat`)**

```bat
@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "INPUT=%~1"
set "OUTDIR=%~2"
set "CODE=%OUTDIR%\code.txt"
set "OUT=%OUTDIR%\output.json"

if not exist "%OUTDIR%" mkdir "%OUTDIR%" >nul 2>&1

REM Count lines in code.txt
set "LINES=0"
if exist "%CODE%" for /f %%N in ('^< "%CODE%" find /v /c ""') do set "LINES=%%N"

> "%OUT%" echo { "ok": true, "metrics": { "line_count": !LINES! } }
exit /b 0
```

**`input.json` example**

```json
{
  "bank": "x91001",
  "reg": "01",
  "addr": "0001",
  "title": "My context title",
  "code_file": "C:\\...\\code.txt",
  "stdin": {}
}
```

**Troubleshooting plugins**

* Check `run.err` if `output.json` wasn’t produced.
* On Windows, run `run.cmd` to reproduce the exact invocation.
* Ensure `plugins/<name>/plugin.json` and entry scripts are **ASCII** (no “smart quotes”).
* Kernel passes **absolute** paths and correctly quotes all args and redirects.

---

## Smoke Tests

### Resolver smoke

`smoke.ps1` verifies the resolver writes the correct lines into the resolved artifact.

```powershell
.\smoke.ps1
# Prints OK on success
```

### Plugin smoke

`plugin-smoke.ps1` drives the CLI, runs a plugin, and asserts `output.json` exists and parses.

```powershell
.\plugin-smoke.ps1
# Prints OK on success
```

> Both scripts are chatty on failure and dump relevant files.

---

## CI (optional)

Add a minimal GitHub Actions workflow: `.github/workflows/ci.yml`

```yaml
name: ci
on: [push, pull_request]
jobs:
  win-mingw:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - name: Enable PS
        shell: pwsh
        run: Set-ExecutionPolicy Bypass -Scope Process -Force
      - name: Install MinGW
        shell: pwsh
        run: choco install mingw -y
      - name: Build
        shell: pwsh
        run: .\build.ps1 -Release
      - name: Resolver smoke
        shell: pwsh
        run: .\smoke.ps1
      - name: Plugin smoke
        shell: pwsh
        run: .\plugin-smoke.ps1
```

---

## Troubleshooting

**Script blocked**
`Set-ExecutionPolicy RemoteSigned -Scope CurrentUser -Force`

**g++ not found**
`choco install mingw -y`

**`g++: missing filename after -o`**
Your `build.ps1` lost `$SRC`/`$EXE`. Use the known-good compile block (it prints `[vars]` for SRC/EXE).

**Banner shows odd chars**
`chcp 65001 >nul` in your wrapper (`clix.cmd`).

**Parse failed: missing '{' after header**
Ensure the bank file header ends with `{` and a matching `}` at the end; BOMs are stripped automatically.

**`xprint(...)` (stray prefix in resolved text)**
Upgrade resolver order: `x.b.r.a` before numeric `b.r.a`, and guard 2-part matches with `(?!\.)`.

**Plugin errors**

* Check `files/out/plugins/.../<plugin>/run.err`
* Open and run `run.cmd`
* Ensure `plugin.json` points to the right `run.bat`/`run.sh`
* Make sure plugin writes **`output.json`**

---

## Advanced configuration

Inside the CLI:

```
:set prefix x
:set base 10
:set widths bank=5 addr=4 reg=2
```

Internally, exports honor the configured widths/base. Changing them affects parsing/formatting of identities, but file content remains plain text.

---

## Security

Plugins are external processes. Treat them as untrusted:

* Review plugin source before running.
* Keep plugins inside your repo (don’t point to system-wide scripts).
* CI should run only trusted plugins.

---

## License

Choose one (MIT / Apache-2.0 / BSD-3-Clause). Add `LICENSE` accordingly.

---

## Appendix A — Mini Grammar (bank files)

```
<ctx>  (<title>){
<reg>
    <addr>  <value>
    <addr>  <value>
<reg>
    <addr>  <value>
}
```

* `<ctx>`: e.g., `x00001` (prefix + base-N with fixed widths)
* `<reg>`: register id (no indent)
* `<addr>`: address id (indented by TAB or SPACE)
* `<value>`: arbitrary UTF-8 text (may contain references)

**References** inside `<value>`:

* `@file(name.txt)`
* `x<bank>.<reg>.<addr>`
* `r<reg>.<addr>` (same bank)
* `x<bank>.<addr>` (reg 01)
* `<bank>.<reg>.<addr>`

---

If you want this README saved into your repo, say the word and I’ll paste it into a `README.md`-ready block you can drop in immediately.
