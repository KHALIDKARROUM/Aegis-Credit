@echo off
setlocal
cd /d "%~dp0"
title Aegis-Credit - Docker

where docker >nul 2>nul
if errorlevel 1 (
    echo Docker Desktop is not installed or is not available.
    echo Install Docker Desktop, start it, and run this file again.
    pause
    exit /b 1
)

docker compose version >nul 2>nul
if errorlevel 1 (
    echo Docker Compose is unavailable. Update Docker Desktop and try again.
    pause
    exit /b 1
)

echo Building and starting Aegis-Credit with PostgreSQL...
where py >nul 2>nul
if not errorlevel 1 (
    py -3 run.py docker-env
) else (
    python run.py docker-env
)
if errorlevel 1 (
    echo Unable to prepare the local Docker environment.
    pause
    exit /b 1
)
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 8; Start-Process 'http://127.0.0.1:8000/'"
docker compose --env-file .aegis-credit-docker.env up --build

endlocal
