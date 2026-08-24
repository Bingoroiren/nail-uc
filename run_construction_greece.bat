@echo off
title Greece Construction Company Email Formatter Launcher
cd /d "%~dp0"
set "PATH=C:\Users\PC\python311\tools;%PATH%"

echo ======================================================
echo         AUTOMATIC PYTHON SETUP AND FORMATTER RUN
echo ======================================================

:: Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 goto NoPython

:: Activate Virtual Environment if it exists
if exist .venv goto ActivateVenv
echo [*] Virtual environment (.venv) not found. Checking system Python...
goto RunScript

:ActivateVenv
echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

:RunScript
echo.
echo ======================================================
echo STEP: Formatting Greece Construction Emails...
echo ======================================================
python format_construction_greece_emails.py %*
if errorlevel 1 goto RunFailed

goto End

:NoPython
echo [ERROR] Python is not installed or not in your PATH.
echo Please install Python 3.8+ and check "Add Python to PATH" during installation.
pause
exit /b

:RunFailed
echo [ERROR] Formatting pipeline failed during execution.
pause
exit /b

:End
echo.
echo ======================================================
echo       GREECE CONSTRUCTION FORMATTING SESSION TERMINATED
echo ======================================================
pause
