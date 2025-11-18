@echo off
title Gamma Lab

echo Launching Gamma Lab...
echo.

REM ===== Check if Python is installed =====
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed or not available in PATH.
    echo Please install Python 3.10 or higher from https://www.python.org/downloads/
    pause
    exit /b
)

REM ===== Get Python version =====
for /f "tokens=2 delims= " %%v in ('python --version') do set PYV=%%v
for /f "tokens=1-3 delims=." %%a in ("%PYV%") do (
    set PYMAJOR=%%a
    set PYMINOR=%%b
    set PYPATCH=%%c
)

echo Python version detected: %PYMAJOR%.%PYMINOR%.%PYPATCH%

REM ===== Validate minimum required Python version: 3.10 =====
if %PYMAJOR% LSS 3 (
    echo [ERROR] Gamma Lab requires Python 3.10 or higher.
    pause
    exit /b
)
if %PYMAJOR%==3 if %PYMINOR% LSS 10 (
    echo [ERROR] Gamma Lab requires Python 3.10 or higher.
    pause
    exit /b
)

echo Python version OK.
echo.

REM ===== Check for virtual environment =====
set INSTALL_DEP=0

IF EXIST ".venv\Scripts\activate" (
    set VENV_PATH=.venv\Scripts\activate
) ELSE (
    IF EXIST "venv\Scripts\activate" (
        set VENV_PATH=venv\Scripts\activate
    ) ELSE (
        echo [INFO] No virtual environment found.
        echo Creating virtual environment...
        python -m venv .venv
        set VENV_PATH=.venv\Scripts\activate
        set INSTALL_DEP=1
    )
)

echo Activating virtual environment...
call %VENV_PATH%

echo.

REM ===== Install dependencies only if the venv was created =====
IF %INSTALL_DEP%==1 (
    echo Installing dependencies for the first time...
    pip install --upgrade pip
    pip install -r requirements.txt
    echo Dependencies installed.
) ELSE (
    echo Virtual environment already exists — skipping dependency installation.
)

echo.
echo Running Gamma Lab...
python main.py
echo.
