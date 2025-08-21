<# 
  Setup-ClaudedRepo.ps1
  Prepares D:\domalecs-os\clix5 for a restricted Claude Code workflow on Windows.

  What it does:
    - Creates local user CLAUDE_LOCAL (non-admin) if missing
    - Tightens ACLs on the repo so CLAUDE_LOCAL and the current admin can write there
    - Creates clix.cmd (wrapper), Start-ClaudeClix.ps1 (launcher), tools.ps1 (orchestrator)
    - Detects Git repo and reports status

  Run as:  PowerShell (Admin)
#>

[CmdletBinding()]
param(
  [string]$RepoPath   = "D:\domalecs-os\clix5",
  [string]$ClaudeExe  = "C:\Program Files\Claude\claude.exe", # adjust if your CLI path differs
  [string]$PythonExe  = "python",                              # or full path, e.g. C:\Python312\python.exe
  [string]$ClaudeUser = "CLAUDE_LOCAL"
)

function Require-Admin {
  $wid = [System.Security.Principal.WindowsIdentity]::GetCurrent()
  $prp = New-Object System.Security.Principal.WindowsPrincipal($wid)
  if (-not $prp.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "Please run this script as Administrator." ; exit 1
  }
}

function Write-Info($msg){ Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Ok($msg){ Write-Host "[ OK ] $msg" -ForegroundColor Green }
function Write-Warn($msg){ Write-Host "[WARN] $msg" -ForegroundColor Yellow }

Require-Admin

# 0) Validate repo path
if (-not (Test-Path $RepoPath)) {
  Write-Error "Repo path not found: $RepoPath" ; exit 1
}
$RepoPath = (Resolve-Path $RepoPath).Path
Write-Info "Using repo: $RepoPath"

# 1) Detect Git-ness
$IsGit = Test-Path (Join-Path $RepoPath ".git")
if (-not $IsGit) {
  try {
    $gitStatus = git -C $RepoPath rev-parse --is-inside-work-tree 2>$null
    if ($LASTEXITCODE -eq 0 -and "$gitStatus".Trim() -eq "true") { $IsGit = $true }
  } catch {}
}
if ($IsGit) { Write-Ok "Git repository detected." } else { Write-Warn "Normal folder (not a Git repo)." }

# 2) Ensure basic subfolders exist (non-destructive)
$dirs = @(
  (Join-Path $RepoPath "bin"),
  (Join-Path $RepoPath "runtime"),
  (Join-Path $RepoPath "runtime\files"),
  (Join-Path $RepoPath "runtime\plugins"),
  (Join-Path $RepoPath "python"),
  (Join-Path $RepoPath "examples")
)
foreach ($d in $dirs) { New-Item -ItemType Directory -Force -Path $d | Out-Null }

# 3) Create clix.cmd (wrapper) if missing
$ClixCmd = Join-Path $RepoPath "clix.cmd"
if (-not (Test-Path $ClixCmd)) {
@"
@echo off
setlocal
set ROOT=%~dp0
pushd "%ROOT%runtime"
"%ROOT%bin\clix.exe" %*
popd
endlocal
"@ | Set-Content -Path $ClixCmd -Encoding ASCII
Write-Ok "Created clix.cmd"
} else { Write-Info "clix.cmd already exists (kept)." }

# 4) Create Start-ClaudeClix.ps1 (launcher) — isolated HOME + working dir = repo
$Launcher = Join-Path $RepoPath "Start-ClaudeClix.ps1"
@"
param(
  [string]`$Repo = "$RepoPath",
  [string]`$ClaudeExe = "$ClaudeExe",
  [string]`$PythonExe = "$PythonExe"
)
`$ErrorActionPreference = 'Stop'
if (-not (Test-Path `$Repo)) { throw "Repo not found: `$Repo" }
if (-not (Test-Path `$ClaudeExe)) { throw "Claude CLI not found: `$ClaudeExe" }

# Isolated HOME / TEMP inside repo
`$IsolatedHome = Join-Path `$Repo ".claude_home"
New-Item -ItemType Directory -Force -Path `$IsolatedHome | Out-Null
`$env:HOME = `$IsolatedHome
`$env:USERPROFILE = `$IsolatedHome
`$env:TEMP = Join-Path `$IsolatedHome "tmp"
`$env:TMP = `$env:TEMP
New-Item -ItemType Directory -Force -Path `$env:TEMP | Out-Null

# Expose repo path to tools
`$env:CLAUDE_WORKSPACE = `$Repo
`$env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine")

# Optionally prepend a specific Python (if `$PythonExe` is a full path, it will be used by your tools.ps1)
Start-Process -FilePath `$ClaudeExe -WorkingDirectory `$Repo
"@ | Set-Content -Path $Launcher -Encoding UTF8
Write-Ok "Created Start-ClaudeClix.ps1"

# 5) Create tools.ps1 (compose → parse → clix)
$Tools = Join-Path $RepoPath "tools.ps1"
if (-not (Test-Path $Tools)) {
@"
param(
  [ValidateSet('prep','compose','parse','clix','all')]
  [string]`$task = 'all',
  [string]`$input = 'auto-compose.txt',
  [string]`$outdir = 'build\generated',
  [string]`$python = '$PythonExe'
)

`$ErrorActionPreference = 'Stop'

function Prep {
  New-Item -ItemType Directory -Force -Path `$outdir | Out-Null
}

function Compose {
  if (-not (Test-Path .\python\compose.py)) { throw "python\compose.py not found" }
  & `$python .\python\compose.py -i ".\examples\`$input" -o "`$outdir"
}

function Parse {
  if (-not (Test-Path .\python\parse_text.py)) { throw "python\parse_text.py not found" }
  & `$python .\python\parse_text.py -i "`$outdir" -o "`$outdir\parsed"
}

function Clix {
  if (-not (Test-Path .\clix.cmd)) { throw "clix.cmd not found" }
  `$script = @"
:open x00001
:ins 0001 generated @ `$outdir
:resolve
:export
:q
"@
  `$script | .\clix.cmd
}

switch (`$task) {
  'prep'    { Prep }
  'compose' { Prep; Compose }
  'parse'   { Prep; Parse }
  'clix'    { Clix }
  'all'     { Prep; Compose; Parse; Clix }
}
"@ | Set-Content -Path $Tools -Encoding UTF8
Write-Ok "Created tools.ps1"
} else { Write-Info "tools.ps1 already exists (kept)." }

# 6) Create restricted local user if missing
$existingUser = Get-LocalUser -Name $ClaudeUser -ErrorAction SilentlyContinue
if (-not $existingUser) {
  Write-Info "Creating local user '$ClaudeUser' (non-admin)…"
  $pw = Read-Host "Set password for $ClaudeUser" -AsSecureString
  New-LocalUser -Name $ClaudeUser -Password $pw -NoPasswordNeverExpires -AccountNeverExpires | Out-Null
  Write-Ok "User '$ClaudeUser' created."
} else {
  Write-Info "User '$ClaudeUser' already exists (kept)."
}

# 7) Tighten ACLs on the repo — only current admin + CLAUDE_LOCAL (and SYSTEM/Admins) have rights
Write-Info "Applying ACLs to restrict writes to repo only…"
icacls $RepoPath /inheritance:d | Out-Null
# Remove generic Users group if present
icacls $RepoPath /remove:g Users 2>$null | Out-Null

# Grant precise rights
$grants = @(
  "$env:UserName:(OI)(CI)F",
  "Administrators:(OI)(CI)M",
  "SYSTEM:(OI)(CI)M",
  "$ClaudeUser:(OI)(CI)F"
)
icacls $RepoPath /grant:r $($grants -join ' ') | Out-Null
Write-Ok "ACLs set."

# 8) Friendly run instructions
$RunAsCmd = "runas /user:$($env:COMPUTERNAME)\$ClaudeUser `"powershell -NoLogo -NoExit -Command `"$Launcher`"`""
Write-Host ""
Write-Ok "SETUP COMPLETE"
Write-Host "Git repo?            : $IsGit"
Write-Host "Repo path            : $RepoPath"
Write-Host "Launcher             : $Launcher"
Write-Host "Wrapper (clix)       : $ClixCmd"
Write-Host "Orchestrator         : $Tools"
Write-Host ""
Write-Host "Launch Claude (restricted user) with:" -ForegroundColor Cyan
Write-Host "  $RunAsCmd" -ForegroundColor White
Write-Host ""
Write-Host "Or open a restricted shell inside repo:" -ForegroundColor Cyan
Write-Host "  runas /user:$($env:COMPUTERNAME)\$ClaudeUser `"cmd /c cd /d $RepoPath && powershell -NoLogo`"" -ForegroundColor White