# plugin-smoke.ps1 — plugin pipeline smoke test (PS 5.1 safe, robust)
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$bin  = Join-Path $root 'bin'
$exe  = Join-Path $bin 'cli-script.exe'

if (-not (Test-Path -LiteralPath $exe)) {
  Write-Host "FAILED: missing $exe (run .\build.ps1 -Release)"
  exit 1
}

$ctx   = 'x98002'
$reg   = '01'
$addr  = '0001'
$plugin= 'python'

# Run dir is created by the kernel on demand
$runDir = Join-Path $bin ("files\out\plugins\{0}\r{1}a{2}\{3}" -f $ctx,$reg,$addr,$plugin)
Remove-Item -Recurse -Force -LiteralPath $runDir -ErrorAction SilentlyContinue | Out-Null

# Drive CLI: list plugins, open ctx, write a line, run plugin
$cmd = @"
:plugins
:open $ctx
:ins $addr one line
:w
:plugin_run $plugin $reg $addr {}
:q
"@

Push-Location $bin
try {
  $cliOut = $cmd | .\cli-script.exe
} finally { Pop-Location }

# Always show CLI output to aid debugging
$cliOut | Write-Host

# Relaxed discovery check (non-fatal): look for "- python @ plugins"
$discovered = $false
if ($cliOut -match "(?im)[-]\s*$plugin\s*@\s*plugins") { $discovered = $true }
if (-not $discovered) {
  Write-Host "`nWARN: plugin '$plugin' not shown by :plugins line (continuing)"
}

# Verify the run dir exists
if (-not (Test-Path -LiteralPath $runDir)) {
  Write-Host "`nFAILED (no plugin run dir): $runDir"
  exit 1
}

$codeTxt    = Join-Path $runDir 'code.txt'
$inputJson  = Join-Path $runDir 'input.json'
$outputJson = Join-Path $runDir 'output.json'
$runLog     = Join-Path $runDir 'run.log'
$runErr     = Join-Path $runDir 'run.err'
$runCmd     = Join-Path $runDir 'run.cmd'

Write-Host "`n-- run dir --"
Get-ChildItem -Force -LiteralPath $runDir

# Kernel-staged files must exist
$missingStage = @()
foreach ($p in @($codeTxt, $inputJson)) {
  if (-not (Test-Path -LiteralPath $p)) { $missingStage += $p }
}
if ($missingStage.Count -gt 0) {
  Write-Host "`nFAILED (kernel did not stage required files):"
  $missingStage | ForEach-Object { Write-Host "  $_" }
  if (Test-Path -LiteralPath $runCmd) { Write-Host "`n-- run.cmd --"; Get-Content -Raw -LiteralPath $runCmd }
  exit 1
}

# output.json must be produced by the plugin
if (-not (Test-Path -LiteralPath $outputJson)) {
  Write-Host "`nFAILED (missing output.json)"
  if (Test-Path -LiteralPath $runCmd) { Write-Host "`n-- run.cmd --"; Get-Content -Raw -LiteralPath $runCmd }
  if (Test-Path -LiteralPath $runErr) { Write-Host "`n-- run.err --"; Get-Content -Raw -LiteralPath $runErr }
  if (Test-Path -LiteralPath $runLog) { Write-Host "`n-- run.log --"; Get-Content -Raw -LiteralPath $runLog }
  exit 1
}

# Validate output.json JSON and content
try {
  $out = Get-Content -Raw -LiteralPath $outputJson | ConvertFrom-Json
} catch {
  Write-Host "`nFAILED (output.json invalid JSON):"
  Get-Content -Raw -LiteralPath $outputJson
  if (Test-Path -LiteralPath $runCmd) { Write-Host "`n-- run.cmd --"; Get-Content -Raw -LiteralPath $runCmd }
  exit 1
}

if (-not $out.ok) {
  Write-Host "`nFAILED (plugin reported ok=false)"
  if (Test-Path -LiteralPath $runLog) { Write-Host "`n-- run.log --"; Get-Content -Raw -LiteralPath $runLog }
  if (Test-Path -LiteralPath $runErr) { Write-Host "`n-- run.err --"; Get-Content -Raw -LiteralPath $runErr }
  exit 1
}

$lineCount = 0
if ($out.metrics -and $out.metrics.line_count) { $lineCount = [int]$out.metrics.line_count }
if ($lineCount -lt 1) {
  Write-Host "`nFAILED (unexpected line_count in output.json):"
  $out | ConvertTo-Json -Depth 6
  if (Test-Path -LiteralPath $runCmd) { Write-Host "`n-- run.cmd --"; Get-Content -Raw -LiteralPath $runCmd }
  exit 1
}

Write-Host "`nOK"
exit 0
