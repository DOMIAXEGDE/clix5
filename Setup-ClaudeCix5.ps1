# Ensure target tools folder exists
if (-not (Test-Path "C:\Tools")) {
    New-Item -Path "C:\" -Name "Tools" -ItemType Directory -Force | Out-Null
}

# Batch script content
$script = @'
@echo off
setlocal enabledelayedexpansion

:: Fixed repo path
set BASEDIR=D:\domalecs-os\clix5

:: Ensure logs folder exists
if not exist "%BASEDIR%\logs" mkdir "%BASEDIR%\logs"

:: Timestamp (YYYYMMDD_HHMMSS)
for /f "tokens=1-4 delims=/ " %%a in ("%date%") do (
    set YYYY=%%d
    set MM=%%b
    set DD=%%c
)
for /f "tokens=1-3 delims=:." %%a in ("%time%") do (
    set HH=%%a
    set MN=%%b
    set SS=%%c
)
set TS=%YYYY%%MM%%DD%_%HH%%MN%%SS%

:: Log file
set LOGFILE=%BASEDIR%\logs\claude-run-%TS%.log

echo Starting Claude session... (logging to %LOGFILE%)

:: Normal run (uses claude.exe on PATH). If you need a full path, replace 'claude.exe' below.
cd /d "%BASEDIR%"
claude.exe > "%LOGFILE%" 2>&1

echo.
echo Claude session finished.
echo Log file saved at:
echo %LOGFILE%

endlocal
'@

# Write the CMD file
$cmdPath = "C:\Tools\claude-cix5.cmd"
Set-Content -Path $cmdPath -Value $script -Encoding ASCII -Force
Write-Host "Created $cmdPath"

# Add C:\Tools to PATH if not already there
$sysPath = [Environment]::GetEnvironmentVariable("Path", "Machine")
if ($sysPath -notmatch [Regex]::Escape("C:\Tools")) {
    Write-Host "Adding C:\Tools to system PATH..."
    $newPath = "$sysPath;C:\Tools"
    [Environment]::SetEnvironmentVariable("Path", $newPath, "Machine")
    Write-Host "PATH updated. You may need to open a new PowerShell or CMD window."
} else {
    Write-Host "C:\Tools already in PATH."
}
