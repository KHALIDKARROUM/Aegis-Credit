@echo off
setlocal
cd /d "%~dp0"
title Aegis-Credit

where py >nul 2>nul
if not errorlevel 1 (
    py -3 run.py %*
) else (
    python run.py %*
)

if errorlevel 1 pause
endlocal
