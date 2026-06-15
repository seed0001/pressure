@echo off
title Household Agent Server
cd /d "%~dp0"
echo Starting Household Agent inside the virtual environment...
"c:\users\aztre\appdata\local\hermes\hermes-agent\venv\Scripts\python.exe" server.py %*
if %errorlevel% neq 0 (
    echo.
    echo Server exited with error code %errorlevel%.
    pause
)
