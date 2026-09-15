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

:: Launch
echo.
echo Starting server... Opening http://127.0.0.1:5000
echo Close this window to stop the server.
start http://127.0.0.1:5000
python run_game.py
pause
