@echo off
title Repair Portugal Hotel Categories
cd /d "%~dp0"

echo ======================================================
echo   REPAIR PORTUGAL HOTEL CATEGORIES IN CSV
echo ======================================================

:: Check virtual environment
if not exist .venv (
    echo [ERROR] Virtual environment .venv not found. Please configure it first.
    pause
    exit /b
)

echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [*] Running category repair script...
python src/repair_hotel_categories.py

echo.
echo ======================================================
echo   REPAIR SESSION COMPLETE
echo ======================================================
pause
