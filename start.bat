@echo off
cd /d "%~dp0"
title J1 Launcher

rem Embedded GPT-SoVITS engine inside this package (engine/)
set "PY=engine\GPT-SoVITS-v2pro-20250604-nvidia50\runtime\python.exe"

echo [1/4] Checking embedded Python...
if not exist "%PY%" (
    echo [ERROR] GPT-SoVITS engine not found in engine\
    echo Please run install.bat first - it downloads and extracts the engine automatically.
    pause
    exit /b 1
)

echo [2/4] Checking Ollama...
where ollama >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Ollama not found. Please run install.bat first.
    pause
    exit /b 1
)
curl -s -m 2 http://127.0.0.1:11434/api/tags >nul 2>nul
if errorlevel 1 (
    echo       Ollama not running, starting in background...
    start "Ollama" /min ollama serve
    timeout /t 3 /nobreak >nul
)

echo [3/4] Checking TTS voice service (GPT-SoVITS)...
curl -s -m 2 http://127.0.0.1:9880/docs >nul 2>nul
if not errorlevel 1 goto tts_ready
echo       TTS not running, starting... first load takes about 1 minute.
start "J1-TTS" /min "%PY%" tools\run_tts_api.py

set /a tries=0
:wait_tts
timeout /t 3 /nobreak >nul
curl -s -m 2 http://127.0.0.1:9880/docs >nul 2>nul
if not errorlevel 1 goto tts_ready
set /a tries+=1
if %tries% geq 60 goto tts_timeout
goto wait_tts

:tts_timeout
echo [WARN] TTS not ready after 3 minutes. Starting panel anyway - chat works, voice may not.
echo        Check logs\tts_api.log for the TTS error.

:tts_ready
curl -s -m 2 http://127.0.0.1:9880/docs >nul 2>nul
if errorlevel 1 (
    echo [WARN] TTS is not responding. Panel will start anyway - chat works, voice may not.
    echo        Check logs\tts_api.log for the TTS error.
) else (
    echo       TTS ready.
)

echo [4/4] Starting J1 panel at http://127.0.0.1:14001 ...
"%PY%" app.py
pause
