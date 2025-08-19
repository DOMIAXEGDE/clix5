$bin = "D:\domalecs-os\clix5\bin\plugins\python"
New-Item -ItemType Directory -Force $bin | Out-Null

# Clean old files
Remove-Item "$bin\*" -Force -ErrorAction SilentlyContinue

# plugin.json (no extra quotes, no paths; just the entry filenames)
@'
{
  "name": "python",
  "entry_win": "run.bat",
  "entry_lin": "run.sh"
}
'@ | Set-Content -LiteralPath "$bin\plugin.json" -Encoding ASCII

# run.bat — robust, pure-ASCII, no fancy punctuation, handles spaces in paths
@'
@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM Args:  %1 = input.json, %2 = outdir (where code.txt lives; write output.json here)
set "INPUT=%~1"
set "OUTDIR=%~2"
set "CODE=%OUTDIR%\code.txt"
set "OUT=%OUTDIR%\output.json"

if not exist "%OUTDIR%" mkdir "%OUTDIR%" >nul 2>&1

REM Count lines in code.txt
set "LINES=0"
if exist "%CODE%" (
  for /f %%N in ('^< "%CODE%" find /v /c ""') do set "LINES=%%N"
)

REM Minimal JSON output
> "%OUT%" (
  echo { "ok": true, "metrics": { "line_count": !LINES! } }
)

exit /b 0
'@ | Set-Content -LiteralPath "$bin\run.bat" -Encoding ASCII

# Optional POSIX script (harmless on Windows)
@'
#!/usr/bin/env sh
INPUT="$1"
OUTDIR="$2"
CODE="$OUTDIR/code.txt"
OUT="$OUTDIR/output.json"

LINES=0
if [ -f "$CODE" ]; then
  LINES=$(wc -l < "$CODE" | tr -d '[:space:]')
fi

printf '{ "ok": true, "metrics": { "line_count": %s } }\n' "$LINES" > "$OUT"
exit 0
'@ | Set-Content -LiteralPath "$bin\run.sh" -Encoding ASCII
