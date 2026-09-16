@echo off
title Novel World Engine
cd /d "%~dp0"

echo ============================================
echo    Novel World - Narrative Engine
echo ============================================
echo.

:: Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install Python 3.10+ from https://python.org first.
    pause
    exit /b 1
)

:: Setup virtual environment if not exists
if not exist venv\Scripts\activate.bat (
    echo [SETUP] Creating virtual environment...
    python -m venv .venv 2>nul
    if not exist .venv\Scripts\python.exe (
        echo [ERROR] venv creation failed. Your Python may lack the venv module.
        echo         Reinstall Python from https://python.org and check "Add pip + venv".
        pause
        exit /b 1
    )
)
call .venv\Scripts\activate.bat

:: Install dependencies if needed
python -c "import flask" 2>nul
if %errorlevel% neq 0 (
    echo [SETUP] Installing dependencies...
    python -m pip install -r requirements.txt -q
    if %errorlevel% neq 0 (
        echo [ERROR] pip install failed. Check your internet connection.
        pause
        exit /b 1
    )
    echo [SETUP] Done.
)

:: Check .env
if not exist .env (
    echo [INFO] .env not found, copying from .env.example ...
    copy .env.example .env >nul
    echo Please fill in OPENAI_API_KEY in the notepad window, save and close to continue.
    notepad .env
    echo Notepad closed, continuing...
)

:: Launch server in a separate window
echo.
echo Starting server...
set USE_WAITRESS=1
start "Novel World Server" ".venv\Scripts\python.exe" run_game.py

:: Wait until backend is ready (poll /api/health, up to 60 seconds)
set "HEALTH_URL=http://127.0.0.1:5000/api/health"
set /a tries=0
:wait_health
set /a tries+=1
if %tries% gtr 60 (
    echo.
    echo [ERROR] Server did not become ready within 60 seconds.
    echo         Please check the "Novel World Server" window for errors
    echo         (e.g. port 5000 occupied, missing dependencies, .env issues).
    pause
    exit /b 1
)
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri '%HEALTH_URL%' -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }"
if errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait_health
)

:: Backend ready -> open browser once
echo.
echo Server is ready. Opening http://127.0.0.1:5000
echo Close the "Novel World Server" window to stop the server.
:: Open browser explicitly: prefer Edge/Chrome executable paths, fallback to default browser
set "URL=http://127.0.0.1:5000"
set "BROWSER="
if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" set "BROWSER=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not defined BROWSER if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" set "BROWSER=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if not defined BROWSER if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "BROWSER=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined BROWSER if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "BROWSER=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if defined BROWSER goto :open_explicit
start "" "%URL%"
goto :browser_done
:open_explicit
start "" "%BROWSER%" "%URL%"
:browser_done
pause
