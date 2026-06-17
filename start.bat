@echo off
title Living Container Server
cd /d "%~dp0"
set "LIVING_CONTAINER_NO_VENV_REDIRECT=1"
set "BUNDLED_PY=C:\Users\aztre\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
set "HERMES_PY=c:\users\aztre\appdata\local\hermes\hermes-agent\venv\Scripts\python.exe"
if exist "%BUNDLED_PY%" (
    set "PYTHON_EXE=%BUNDLED_PY%"
) else (
    set "PYTHON_EXE=%HERMES_PY%"
)
echo Starting Living Container...
"%PYTHON_EXE%" server.py %*
if %errorlevel% neq 0 (
    echo.
    echo Server exited with error code %errorlevel%.
    pause
)
