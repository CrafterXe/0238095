@echo off
setlocal EnableExtensions
rem ============================================================
rem  J1 one-click launcher (portable, no absolute paths).
rem  Everything is resolved from this script's own folder (%~dp0):
rem    [1/4] locate embedded GPT-SoVITS python (engine\*\runtime\python.exe)
rem    [2/4] ensure Ollama is running          (port 11434)
rem    [3/4] ensure TTS GPT-SoVITS api_v2      (port 9880)
rem    [4/4] run the J1 Gradio panel           (port 14001, foreground)
rem  IMPORTANT: keep this file saved as CRLF + ASCII.
rem  A .bat with LF-only endings breaks "goto" labels on Windows.
rem ============================================================

pushd "%~dp0"
if errorlevel 1 exit /b 1
title J1 Launcher

rem ---- probe tool: prefer curl.exe, fall back to PowerShell ----
set "HAVE_CURL="
curl.exe --version >nul 2>nul && set "HAVE_CURL=1"

echo [1/4] Checking embedded Python - GPT-SoVITS engine...
set "PY="
for /d %%D in ("engine\*") do (
    if not defined PY if exist "%%~fD\runtime\python.exe" set "PY=%%~fD\runtime\python.exe"
)
if not defined PY (
    echo [ERROR] GPT-SoVITS engine not found under engine\.
    echo         Run install.bat first - it downloads and extracts the engine.
    pause
    popd
    exit /b 1
)
echo       Python: %PY%

echo [2/4] Checking Ollama...
set "OLLAMA="
where ollama >nul 2>nul && set "OLLAMA=ollama"
if not defined OLLAMA if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
if not defined OLLAMA if exist "%ProgramFiles%\Ollama\ollama.exe" set "OLLAMA=%ProgramFiles%\Ollama\ollama.exe"
if not defined OLLAMA (
    echo [ERROR] Ollama not found. Please run install.bat first.
    pause
    popd
    exit /b 1
)
call :check_url "http://127.0.0.1:11434/api/tags"
if errorlevel 1 (
    echo       Ollama not running, starting in background...
    start "Ollama" /min "%OLLAMA%" serve
    call :sleep 3
) else (
    echo       Ollama already running.
)

echo [3/4] Checking TTS voice service - GPT-SoVITS api_v2...
call :check_url "http://127.0.0.1:9880/docs"
if not errorlevel 1 (
    echo       TTS already running.
    goto tts_ready
)
echo       TTS not running, starting background window - first load takes about 1 minute...
if not exist "generated" mkdir "generated"
start "J1-TTS" /min "%PY%" "%~dp0tools\run_tts_api.py"

set /a TTS_TRIES=0
:wait_tts
call :sleep 3
call :check_url "http://127.0.0.1:9880/docs"
if not errorlevel 1 goto tts_ready
<nul set /p "=."
set /a TTS_TRIES+=1
if %TTS_TRIES% geq 60 goto tts_timeout
goto wait_tts

:tts_timeout
echo.
echo [WARN] TTS not ready after 3 minutes. Starting panel anyway...
echo        Chat still works, voice may not.
echo        Check the J1-TTS window or logs\tts_api.log.
goto panel_start

:tts_ready
echo.
echo       TTS ready.

:panel_start
echo [4/4] Starting J1 panel at http://127.0.0.1:14001 ...
"%PY%" "%~dp0app.py"
echo.
echo Panel stopped.
pause
popd
exit /b 0

:sleep
rem wait ~N seconds; ping-based so it works even with redirected stdin
set /a SLEEP_TICKS=%1 + 1
ping -n %SLEEP_TICKS% 127.0.0.1 >nul
set "SLEEP_TICKS="
exit /b

:check_url
rem probe %~1 - errorlevel 0 means reachable, 1 means not
if defined HAVE_CURL goto check_url_curl
powershell -NoProfile -Command "try{ Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri '%~1' | Out-Null; exit 0 }catch{ exit 1 }"
exit /b
:check_url_curl
curl.exe -s -m 2 -o NUL "%~1" 2>NUL
exit /b
