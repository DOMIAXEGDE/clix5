param(
  [switch]$Release,
  [switch]$Run,
  [switch]$Clean,
  [string]$Cxx = "g++",
  [ValidateSet('c++17','c++20','c++23')]
  [string]$Std = "c++23",
  [switch]$Static = $true,
  [string]$OutDirName = "bin"
)

$ErrorActionPreference = 'Stop'
$ROOT = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Item -LiteralPath $MyInvocation.MyCommand.Path).DirectoryName }
$OUT  = Join-Path $ROOT $OutDirName
$CFG  = if ($Release) { "release" } else { "debug" }

function Ensure-Dir($p){
  if (-not (Test-Path -LiteralPath $p)) {
    New-Item -ItemType Directory -Force -Path $p | Out-Null
  }
}

if ($Clean) {
  if (Test-Path -LiteralPath $OUT) { Remove-Item -Recurse -Force $OUT }
  Write-Host "[clean] done."
  if (-not $Run) { return }
}

# ---- Discover g++ and version (PS 5.1 safe) ----
$gxx = Get-Command $Cxx -ErrorAction SilentlyContinue
if (-not $gxx) { throw "Compiler '$Cxx' not found in PATH. If needed: choco install mingw -y" }

$gccVerText = ""
try { $gccVerText = & $Cxx -dumpfullversion } catch {}
if (-not $gccVerText) { try { $gccVerText = & $Cxx -dumpversion } catch {} }

$gccVerShown = "<unknown>"
if ($gccVerText) { $gccVerShown = $gccVerText }

Write-Host ("[compiler] {0}  version {1}" -f $gxx.Source, $gccVerShown)

$gccVer = [Version]"0.0.0"
if ($gccVerText) {
  try {
    $clean = ($gccVerText -replace '[^\d\.]','')
    if ($clean) { $gccVer = [Version]$clean }
  } catch {}
}

# ---- Seed minimal plugin & context if missing ----
$PluginsRoot = Join-Path $ROOT "plugins"
$FilesRoot   = Join-Path $ROOT "files"
$PyDir       = Join-Path $PluginsRoot "python"
Ensure-Dir $PluginsRoot
Ensure-Dir $FilesRoot
Ensure-Dir (Join-Path $FilesRoot "out")

if (-not (Test-Path -LiteralPath (Join-Path $PyDir "plugin.json"))) {
  Ensure-Dir $PyDir
@'
{
  "name": "python",
  "entry_win": "run.bat",
  "entry_lin": "run.sh"
}
'@ | Set-Content -LiteralPath (Join-Path $PyDir "plugin.json") -Encoding UTF8
}

if (-not (Test-Path -LiteralPath (Join-Path $PyDir "run.bat"))) {
@'
@echo off
setlocal ENABLEEXTENSIONS ENABLEDELAYEDEXPANSION
REM Usage: run.bat <input.json> <output_dir>

set "IN=%~1"
set "OUT=%~2"

if not exist "%IN%" (
  echo [plugin] ERROR: input.json not found: %IN% 1>&2
  exit /b 1
)
if not exist "%OUT%" mkdir "%OUT%" 2>nul

for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command ^
  "(Get-Content -Raw '%IN%') | ConvertFrom-Json | Select-Object -ExpandProperty code_file"`) do set "CODE_FILE=%%A"

if not defined CODE_FILE (
  echo [plugin] ERROR: code_file not found in input.json 1>&2
  exit /b 2
)
if not exist "%CODE_FILE%" (
  echo [plugin] ERROR: code_file does not exist: %CODE_FILE% 1>&2
  exit /b 3
)

for /f "usebackq delims=" %%L in (`powershell -NoProfile -Command ^
  "(Get-Content -Raw -LiteralPath '%CODE_FILE%') -split \"`r?`n\" | Measure-Object | %% Count"`) do set "LINES=%%L"
if not defined LINES set "LINES=0"

powershell -NoProfile -Command ^
  "$o = @{ ok=$true; tool='python'; summary='counted lines in code_file'; metrics=@{ line_count = %LINES% } }; " ^
  "$o | ConvertTo-Json | Out-File -Encoding utf8 -LiteralPath (Join-Path '%OUT%' 'output.json')"

exit /b 0
'@ | Set-Content -LiteralPath (Join-Path $PyDir "run.bat") -Encoding ASCII
}

# seed a proper starter context if none exists (UTF-8 without BOM)
$DemoCtx = Join-Path $FilesRoot "x00001.txt"
if (-not (Test-Path -LiteralPath $DemoCtx)) {
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  $content = @"
x00001 (demo context){
`t0001`tprint("hello")
}
"@
  [System.IO.File]::WriteAllText($DemoCtx, $content, $utf8NoBom)
}

$COMMON = @("-std=$Std","-Wall","-Wextra","-pedantic","-DNOMINMAX","-DWIN32_LEAN_AND_MEAN","-finput-charset=utf-8","-fexec-charset=utf-8")
$DBG    = @("-O0","-g3")
$REL    = @("-O2","-DNDEBUG","-s")
if ($Static) { $REL += @("-static-libstdc++","-static-libgcc") }
$CFLAGS = $COMMON + ($(if($Release){$REL}else{$DBG}))

$LFLAGS = @()
$needFs = ($Std -eq 'c++17') -and ($gccVer.Major -lt 9)
if ($needFs) { $LFLAGS += "-lstdc++fs" }


# --- compile ---------------------------------------------------------------
Ensure-Dir $OUT
Ensure-Dir (Join-Path $OUT "plugins")
Ensure-Dir (Join-Path $OUT "files")
Ensure-Dir (Join-Path $OUT "files\out")

$SRC = Join-Path $ROOT "scripted.cpp"
$EXE = Join-Path $OUT  "cli-script.exe"

# Sanity prints
Write-Host "[vars] ROOT=$ROOT"
Write-Host "[vars] OUT =$OUT"
Write-Host "[vars] SRC =$SRC"
Write-Host "[vars] EXE =$EXE"

if (-not (Test-Path -LiteralPath $SRC)) { throw "SRC not found: $SRC" }

# CFLAGS / LFLAGS must be set *before* this block:
# $CFLAGS = $COMMON + ($(if($Release){$REL}else{$DBG}))
# $LFLAGS = @() ; if ($needFs) { $LFLAGS += "-lstdc++fs" }

$cmdLine = @($Cxx) + $CFLAGS + @($SRC, "-o", $EXE) + $LFLAGS
Write-Host "[build] $($cmdLine -join ' ')"

& $Cxx @CFLAGS $SRC "-o" $EXE @LFLAGS
if ($LASTEXITCODE -ne 0) { throw "g++ failed with exit code $LASTEXITCODE" }

Write-Host "[build] ok -> $EXE"


# ---- Stage runtime folders -------------------------------------------------
Write-Host "[stage] plugins -> $(Join-Path $OUT 'plugins')"
Copy-Item -Recurse -Force -Path (Join-Path $PluginsRoot "*") -Destination (Join-Path $OUT "plugins")

Write-Host "[stage] files   -> $(Join-Path $OUT 'files')"
Copy-Item -Recurse -Force -Path (Join-Path $FilesRoot "*")   -Destination (Join-Path $OUT "files")

# ---- Run (optional) with UTF-8 console ------------------------------------
if ($Run) {
  Write-Host "[run] $EXE  (working directory: $OUT)"
  Push-Location $OUT
  try {
    try { chcp 65001 >$null } catch {}
    try {
      $utf8 = New-Object System.Text.UTF8Encoding($false)
      [Console]::OutputEncoding = $utf8
      $script:OutputEncoding = $utf8
    } catch {}
    & $EXE
  } finally {
    Pop-Location
  }
}
