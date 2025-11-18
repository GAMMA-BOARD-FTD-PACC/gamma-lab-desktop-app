@echo off
setlocal enabledelayedexpansion
title Gamma Lab

echo Launching Gamma Lab...
echo.

REM ==========================================
REM GET LIST OF INSTALLED PYTHON VERSIONS
REM ==========================================
py -0 > py_list.tmp 2>nul

IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python Launcher not found. Please install Python 3.11.
    pause
    exit /b
)

set FOUND311=0

for /f "tokens=1" %%v in (py_list.tmp) do (
    echo %%v | find "3.11" >nul
    if !ERRORLEVEL! == 0 (
        set FOUND311=1
    )
)

del py_list.tmp


REM ==========================================
REM VERIFY PYTHON 3.11 IS INSTALLED
REM ==========================================
if %FOUND311%==0 (
    echo [ERROR] No Python 3.11.x installation detected.
    echo Please install Python 3.11 from:
    echo https://www.python.org/downloads/release/python-3110/
    pause
    exit /b
)

echo Python 3.11 detected.
echo.


REM ==========================================
REM CREATE OR USE VIRTUAL ENVIRONMENT
REM ==========================================
set INSTALL_DEP=0

IF EXIST ".venv\Scripts\activate" (
    set VENV_PATH=.venv\Scripts\activate
) ELSE IF EXIST "venv\Scripts\activate" (
    set VENV_PATH=venv\Scripts\activate
) ELSE (
    echo Creating virtual environment with Python 3.11...
    py -3.11 -m venv .venv
    set VENV_PATH=.venv\Scripts\activate
    set INSTALL_DEP=1
)

echo Activating virtual environment...
call %VENV_PATH%
echo.

echo Installing dependencies...
pip install --upgrade pip
pip install -r requirements.txt
echo Dependencies installed.


REM ==========================================
REM RUN APPLICATION
REM ==========================================
echo Running Gamma Lab...
py -3.11 main.py
echo.

pause >nul
