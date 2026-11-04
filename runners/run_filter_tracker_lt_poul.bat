@echo off
chcp 65001 >nul
cd /d "%~dp0\.."

echo ======================================================================
echo  CROSS-CHECK AND CLEAN LT POULTRY DATASET WITH MAIL TRACKER
echo ======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment python.exe not found!
    pause
    exit /b 1
)

.venv\Scripts\python.exe crawlmail\filter_tracker_lt_poul.py

echo.
echo Process completed!
pause

