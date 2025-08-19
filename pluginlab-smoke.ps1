# pluginlab-smoke.ps1 — extended plugin lab smoke (PS 5.1 safe, ASCII only)
$ErrorActionPreference = 'Stop'

function Fail([string]$msg) {
  Write-Host ""
  Write-Host ("FAILED: {0}" -f $msg)
  exit 1
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$bin  = Join-Path $root 'bin'
$exe  = Join-Path $bin 'cli-script.exe'
if (-not (Test-Path -LiteralPath $exe)) { Fail ("missing {0} (run .\build.ps1 -Release)" -f $exe) }

$plugin = 'python'
$reg    = '01'

# ---------- helpers ----------
function Run-CLI([string]$text) {
  Push-Location $bin
  try { return ($text | .\cli-script.exe) } finally { Pop-Location }
}
function RunDir([string]$ctx,[string]$addr,[string]$plug) {
  Join-Path $bin ("files\out\plugins\{0}\r{1}a{2}\{3}" -f $ctx,$reg,$addr,$plug)
}
function Assert-Output([string]$ctx,[string]$addr,[int]$expected,[string]$label) {
  $rd = RunDir $ctx $addr $plugin
  $outJson = Join-Path $rd 'output.json'
  $runCmd  = Join-Path $rd 'run.cmd'
  $runErr  = Join-Path $rd 'run.err'
  $runLog  = Join-Path $rd 'run.log'

  if (-not (Test-Path -LiteralPath $rd)) {
    Fail ("{0}: run dir not created: {1}" -f $label, $rd)
  }
  if (-not (Test-Path -LiteralPath $outJson)) {
    Write-Host "`n-- run dir --"
    Get-ChildItem -Force -LiteralPath $rd
    if (Test-Path -LiteralPath $runCmd) { Write-Host "`n-- run.cmd --"; Get-Content -Raw -LiteralPath $runCmd }
    if (Test-Path -LiteralPath $runErr) { Write-Host "`n-- run.err --"; Get-Content -Raw -LiteralPath $runErr }
    if (Test-Path -LiteralPath $runLog) { Write-Host "`n-- run.log --"; Get-Content -Raw -LiteralPath $runLog }
    Fail ("{0}: plugin did not produce output.json" -f $label)
  }

  try { $j = Get-Content -Raw -LiteralPath $outJson | ConvertFrom-Json }
  catch {
    Write-Host "`n-- output.json --"
    Get-Content -Raw -LiteralPath $outJson
    Fail ("{0}: output.json is not valid JSON" -f $label)
  }

  if (-not $j.ok) {
    Write-Host "`n-- output.json --"
    $j | ConvertTo-Json -Depth 6
    Fail ("{0}: plugin ok=false" -f $label)
  }

  $n = 0
  if ($j.metrics -and $j.metrics.line_count) { $n = [int]$j.metrics.line_count }
  if ($n -ne $expected) {
    Write-Host "`n-- output.json --"
    $j | ConvertTo-Json -Depth 6
    Fail ("{0}: expected line_count={1}, got {2}" -f $label, $expected, $n)
  }

  Write-Host ("OK  {0}: line_count={1}" -f $label,$n)
}

# ---------- ensure plugin is discoverable (non-fatal warn only) ----------
$disc = Run-CLI ":plugins`n:q`n"
if ($disc -notmatch "(?im)[-]\s*$plugin\s*@\s*plugins") {
  Write-Host ("WARN: plugin '{0}' not shown by :plugins (continuing)" -f $plugin)
}

# ---------- prepare lab include + stdin file ----------
$lab1 = Join-Path $bin 'files\lab_multiline_3.txt'
$lab2 = Join-Path $bin 'files\lab_multiline_5.txt'
$stdinFile = Join-Path $bin 'files\stdin_lab.json'

"one`r`ntwo`r`nthree`r`n" | Set-Content -LiteralPath $lab1 -Encoding ASCII
"1`r`n2`r`n3`r`n4`r`n5`r`n" | Set-Content -LiteralPath $lab2 -Encoding ASCII
'{"note":"from-file","case":2}' | Set-Content -LiteralPath $stdinFile -Encoding ASCII

# ---------- matrix of cases ----------
$cases = @(
  # Case 1: ctx x99001, single line, inline empty stdin
  @{ Ctx='x99001'; Addr='0001'; Value='alpha';                         Stdin='{}';                        Expect=1; Label='ctx1-single-inline' },

  # Case 2: ctx x99001, multiline via @file (3 lines), inline JSON (no spaces)
  @{ Ctx='x99001'; Addr='0002'; Value='@file(lab_multiline_3.txt)';    Stdin='{"mode":"count"}';          Expect=3; Label='ctx1-multiline-inline' },

  # Case 3: ctx x99002, multiline via @file (5 lines), stdin from file
  @{ Ctx='x99002'; Addr='0003'; Value='@file(lab_multiline_5.txt)';    Stdin='files\stdin_lab.json';      Expect=5; Label='ctx2-multiline-stdinfile' }
)

# ---------- run all cases ----------
foreach ($c in $cases) {
  $ctx   = $c.Ctx
  $addr  = $c.Addr
  $val   = $c.Value
  $stdin = $c.Stdin
  $label = $c.Label
  $expect = [int]$c.Expect

  # Clean prior run dir
  $rd = RunDir $ctx $addr $plugin
  Remove-Item -Recurse -Force -LiteralPath $rd -ErrorAction SilentlyContinue | Out-Null

  # Drive CLI (value is rest-of-line; spaces ok; inline JSON has no spaces)
  $cli = @"
:open $ctx
:ins $addr $val
:w
:plugin_run $plugin $reg $addr $stdin
:q
"@

  $out = Run-CLI $cli
  $out | Write-Host

  # Validate output.json + metrics.line_count
  Assert-Output $ctx $addr $expect $label
}

Write-Host "`nALL OK - plugin lab smoke passed."
exit 0
