@echo off
title Eve Agent V2 Unleashed — Web Terminal
cd /d "%~dp0"
echo.
echo   ████ EVE V2 UNLEASHED ████
echo   Starting server...
echo.

:: Kill any stale process holding port 7777
for /f "tokens=5" %%p in ('netstat -aon 2^>nul ^| findstr ":7777 " ^| findstr "LISTENING"') do (
    echo   Releasing port 7777 ^(PID %%p^)...
    taskkill /F /PID %%p >nul 2>&1
)

:: Open browser in background after server warmup
start /b cmd /c "timeout /t 6 /nobreak > nul & start http://localhost:7777"

echo   Eve will open at http://localhost:7777 in ~6 seconds.
echo   Press Ctrl+C to stop.
echo.

:: Run Python in the foreground — Ctrl+C kills it cleanly, port 7777 releases on exit
python eve_server.py
