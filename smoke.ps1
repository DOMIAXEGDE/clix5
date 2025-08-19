# smoke.ps1 — resolver + export smoke test (PS 5.1 safe)
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$bin  = Join-Path $root 'bin'
$exe  = Join-Path $bin 'cli-script.exe'

if (-not (Test-Path -LiteralPath $exe)) {
  Write-Host "FAILED: missing $exe (run .\build.ps1 -Release)"
  exit 1
}

# Test context and artifacts
$ctx = 'x98001'
$resPath  = Join-Path $bin "files\out\$ctx.resolved.txt"
$jsonPath = Join-Path $bin "files\out\$ctx.json"
$ctxPath  = Join-Path $bin "files\$ctx.txt"
$incFile  = Join-Path $bin "files\hello.txt"

# Clean slate
Remove-Item -LiteralPath $resPath  -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $jsonPath -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $ctxPath  -ErrorAction SilentlyContinue
Set-Content -LiteralPath $incFile -Encoding ASCII -Value "INCLUDED"

# Drive CLI
$cmd = @"
:open $ctx
:ins 0001 alpha
:insr 02 0000 $ctx.01.0001
:insr 02 0002 @file(hello.txt)
:w
:resolve
:export
:r files/out/$ctx.resolved.txt
:show
:q
"@

Push-Location $bin
try {
  $out = $cmd | .\cli-script.exe
  $out | Write-Host
} finally { Pop-Location }

# Check resolved file
if (-not (Test-Path -LiteralPath $resPath)) {
  Write-Host "FAILED (no resolved file): $resPath"
  exit 1
}

$content = Get-Content -Raw -LiteralPath $resPath

# Expect: reg 02 has 0000 -> alpha (same-bank resolution)
if ($content -notmatch '(?m)^\s*02\s*\r?\n[ \t]+0000[ \t]+alpha\b') {
  Write-Host "FAILED: reg 02/0000 did not resolve to 'alpha'"
  Write-Host "`n---- resolved file ----"
  Write-Host $content
  exit 1
}

# Expect: reg 02 has 0002 -> INCLUDED (from @file)
if ($content -notmatch '(?m)^\s*02\s*\r?\n(?:.*\r?\n)*[ \t]+0002[ \t]+INCLUDED\b') {
  Write-Host "FAILED: reg 02/0002 did not include 'INCLUDED'"
  Write-Host "`n---- resolved file ----"
  Write-Host $content
  exit 1
}

# Check exported JSON parses
if (-not (Test-Path -LiteralPath $jsonPath)) {
  Write-Host "FAILED (no export JSON): $jsonPath"
  exit 1
}
try {
  $j = Get-Content -Raw -LiteralPath $jsonPath | ConvertFrom-Json
} catch {
  Write-Host "FAILED (export JSON not valid):"
  Get-Content -Raw -LiteralPath $jsonPath
  exit 1
}

Write-Host "OK"
exit 0
