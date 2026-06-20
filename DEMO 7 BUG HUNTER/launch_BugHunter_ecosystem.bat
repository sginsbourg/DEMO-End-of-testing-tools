@echo off
SETLOCAL Enabledelayedexpansion

echo 🐳 Checking if Docker Desktop is running...
docker ps >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ Docker is already active.
    goto :LAUNCH_APP
)

echo 🚀 Launching Docker Desktop...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"

echo ⏳ Waiting for the Docker Engine daemon to respond...
set counter=0
:WAIT_LOOP
timeout /t 3 /nobreak >nul
docker ps >nul 2>&1
if %errorlevel% neq 0 (
    set /a counter+=1
    echo   [.!counter!.] Still initializing engine...
    if !counter! gtr 40 (
        echo ❌ Timeout: Docker Desktop failed to start within 2 minutes.
        pause
        exit /b 1
    )
    goto :WAIT_LOOP
)

echo ✅ Docker Daemon is ready!

:LAUNCH_APP
echo 📦 Navigating to workspace...
cd /d "%~dp0bughunter-web-app"

echo 🌐 Launching BugHunter Web UI portal...
:: Opens your system's default web browser to your application dashboard
start http://localhost:3000

echo 🛠️ Starting BugHunter ecosystem orchestration...
docker-compose up --build

pause
