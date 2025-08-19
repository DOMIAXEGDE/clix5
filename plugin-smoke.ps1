# plugin-smoke.ps1 — plugin pipeline smoke test (PS 5.1 safe)
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$bin  = Join-Path $root 'bin'
$exe  = Join-Path $bin 'cli-script.exe'

if (-not (Test-Path -LiteralPath $exe)) {
  Write-Host "FAILED: missing $exe (run .\build.ps1 -Release)"
  exit 1
}

$ctx = 'x98002'
$reg = '01'
$addr = '0001'
$plugin = 'python'

# Stage fresh run area (plugin run dir is created by kernel on demand)
$runDir = Join-Path $bin "files\out\plugins\$ctx\r${reg}a$addr\$plugin"
Remove-Item -Recurse -Force -LiteralPath $runDir -ErrorAction SilentlyContinue | Out-Null

# Drive CLI (discover plugin, open ctx, write a line, run plugin)
$cmd = @"
:plugins
:open $ctx
:ins $addr line one
:w
:plugin_run $plugin $reg $addr {}
:q
"@

Push-Location $bin
try {
  $cliOut = $cmd | .\cli-script.exe
  $cliOut | Write-Host
} finally { Pop-Location }

# Sanity: plugin discovered?
if ($cliOut -notmatch "(?m)^\s*-\s*$plugin\s*@\s*plugins") {
  Write-Host "FAILED: plugin '$plugin' not discovered by :plugins"
  exit 1
}

# Did the kernel create the run dir?
if (-not (Test-Path -LiteralPath $runDir)) {
  Write-Host "FAILED (no plugin run dir): $runDir"
  exit 1
}

# Must have these files; output.json is produced by the plugin
$codeTxt    = Join-Path $runDir 'code.txt'
$inputJson  = Join-Path $runDir 'input.json'
$outputJson = Join-Path $runDir 'output.json'
$runLog     = Join-Path $runDir 'run.log'
$runErr     = Join-Path $runDir 'run.err'
$runCmd     = Join-Path $runDir 'run.cmd'

Write-Host "`n-- run dir --"
Get-ChildItem -Force -LiteralPath $runDir

# Check presence
$missing = @()
foreach ($p in @($codeTxt, $inputJson)) {
  if (-not (Test-Path -LiteralPath $p)) { $missing += $p }
}
if ($missing.Count -gt 0) {
  Write-Host "`nFAILED (kernel did not stage required files):"
  $missing | ForEach-Object { Write-Host "  $_" }
  exit 1
}

# If output.json missing, show diagnostics and fail
if (-not (Test-Path -LiteralPath $outputJson)) {
  Write-Host "`nFAILED (missing output.json)"
  if (Test-Path -LiteralPath $runCmd) { Write-Host "`n-- run.cmd --"; Get-Content -Raw -LiteralPath $runCmd }
  if (Test-Path -LiteralPath $runErr) { Write-Host "`n-- run.err --"; Get-Content -Raw -LiteralPath $runErr }
  if (Test-Path -LiteralPath $runLog) { Write-Host "`n-- run.log --"; Get-Content -Raw -LiteralPath $runLog }
  exit 1
}

# Validate output.json parses and has ok=true and metrics.line_count >= 1
try {
  $out = Get-Content -Raw -LiteralPath $outputJson | ConvertFrom-Json
} catch {
  Write-Host "`nFAILED (output.json invalid JSON):"
  Get-Content -Raw -LiteralPath $outputJson
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
  exit 1
}

Write-Host "`nOK"
exit 0
