# smoke.ps1 — verify the resolver end-to-end using the resolved text file
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$bin  = Join-Path $root 'bin'
$ctx  = 'x90011'

# fresh start
Remove-Item (Join-Path $bin "files\$ctx.txt") -ErrorAction SilentlyContinue
Remove-Item (Join-Path $bin "files\out\$ctx.resolved.txt") -ErrorAction SilentlyContinue

# drive the CLI non-interactively
$cmd = @"
:open $ctx
:ins 0001 hello
:insr 02 0000 $ctx.01.0001
:w
:resolve
:q
"@

Push-Location $bin
try {
  $null = $cmd | .\cli-script.exe
} finally {
  Pop-Location
}

# read the resolved artifact and assert the value actually resolved
$resFile = Join-Path $bin "files\out\$ctx.resolved.txt"
if (-not (Test-Path $resFile)) {
  Write-Host "FAILED (no resolved file): $resFile"
  exit 1
}

$content = Get-Content -Raw $resFile
# Look for the register-02 block and address 0000 resolved to 'hello'
# (multiline regex: a line "02", then an indented "0000    hello")
if ($content -match '(?m)^\s*02\s*\r?\n[ \t]+0000[ \t]+hello\b') {
  Write-Host "OK"
  exit 0
} else {
  Write-Host "FAILED"
  Write-Host "---- resolved file ----"
  Write-Host $content
  exit 1
}
