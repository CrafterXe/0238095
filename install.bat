@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title J1 Installer

rem ============================================================
rem  J1 one-click installer.
rem  Works on a FRESH machine with NO Python and NO Ollama:
rem   Step A (this .bat, pure batch + curl + 7zr, no Python needed):
rem       download + extract the GPT-SoVITS engine -> gives us an
rem       embedded python.exe to run the rest.
rem   Step B (install.py, run by that embedded python):
rem       voice models + Ollama + chat model.
rem ============================================================

set "ENGINE_DIRNAME=GPT-SoVITS-v2pro-20250604-nvidia50"
set "ENGINE_TARGET=engine\%ENGINE_DIRNAME%"
set "RUNTIME_PY=%ENGINE_TARGET%\runtime\python.exe"
set "PKG=engine\%ENGINE_DIRNAME%.7z"
set "SEVENZR=tools\7zr.exe"
set "URL1=https://hf-mirror.com/lj1995/GPT-SoVITS-windows-package/resolve/main/GPT-SoVITS-v2pro-20250604-nvidia50.7z"
set "URL2=https://huggingface.co/lj1995/GPT-SoVITS-windows-package/resolve/main/GPT-SoVITS-v2pro-20250604-nvidia50.7z"

echo [A] Checking GPT-SoVITS engine ...
if exist "%RUNTIME_PY%" (
    echo       engine ready.
    goto :have_py
)

echo       engine not found, downloading ^(about 8.2 GB, needs internet/VPN^)...
if not exist "engine" mkdir "engine"

rem --- download with curl (follows redirects, resumes with -C -) ---
set "DL_OK="
for %%U in ("%URL1%" "%URL2%") do (
    if not defined DL_OK (
        echo       trying source: %%~U
        curl.exe -L -C - --retry 3 --retry-delay 5 -A "Mozilla/5.0" -o "%PKG%.part" "%%~U"
        if exist "%PKG%.part" (
            rem sanity: file should be large (engine is GB-scale)
            for %%S in ("%PKG%.part") do if %%~zS GTR 1000000000 (
                move /y "%PKG%.part" "%PKG%" >nul
                set "DL_OK=1"
            )
        )
    )
)

if not defined DL_OK (
    echo [ERROR] engine download failed.
    echo   Please manually download this file and place it at: %PKG%
    echo     %URL2%
    echo   Then run this file again.
    pause
    exit /b 1
)

if not exist "%SEVENZR%" (
    echo [ERROR] extractor missing: %SEVENZR% ^(should ship with the package^)
    echo   Please extract %PKG% into the engine\ folder manually with 7-Zip.
    pause
    exit /b 1
)
echo       extracting ^(a few minutes, please wait^)...
"%SEVENZR%" x "%PKG%" -o"engine" -y >nul
if errorlevel 1 (
    echo [ERROR] extraction failed. Try extracting %PKG% into engine\ manually.
    pause
    exit /b 1
)
del /q "%PKG%" >nul 2>nul

if not exist "%RUNTIME_PY%" (
    echo [ERROR] extraction done but runtime python not found at %RUNTIME_PY%
    echo   Check the engine\ folder structure.
    pause
    exit /b 1
)
echo       engine extracted.

:have_py
rem ============================================================
rem  Step B: pick a working python -> run install.py for the rest.
rem  Prefer the embedded engine python (has torch/gradio/... built in).
rem  Fallback to system python / py launcher if the embedded one fails.
rem ============================================================
echo.
echo [B] Engine python ready, continuing setup (voice model / Ollama / chat model)...

set "PYCMD=%RUNTIME_PY%"
"%RUNTIME_PY%" -c "import sys" >nul 2>nul
if errorlevel 1 (
    echo       embedded python broken, trying system python...
    set "PYCMD="
    where python >nul 2>nul && set "PYCMD=python"
    if not defined PYCMD ( where py >nul 2>nul && set "PYCMD=py -3" )
)

if not defined PYCMD (
    echo [ERROR] No working Python found to continue setup.
    echo   The embedded engine python is broken AND no system Python is installed.
    echo   Easiest fix: install Python 3.8+ and check "Add to PATH":
    echo     https://www.python.org/downloads/
    echo   Then run this file again.
    pause
    exit /b 1
)

%PYCMD% "%~dp0install.py"
echo.
pause
