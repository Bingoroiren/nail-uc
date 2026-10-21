@echo off
chcp 65001 >nul
title PersonalneAgentury.sk - 3,405 Companies API Harvester
echo =======================================================================
echo   CRAWL ALL 3,405 COMPANIES FROM PERSONALNEAGENTURY.SK VIA FAST API
echo   100%% Independent Dataset - No Cloudflare Block - Auto-Resume
echo =======================================================================
echo.

cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Python virtual environment not found in .venv!
    pause
    exit /b 1
)

echo Starting fast API crawl...
.venv\Scripts\python.exe crawlmail\harvest_personalneagentury_api.py

echo.
echo =======================================================================
echo   PROCESS FINISHED!
echo   Output files:
echo   - SK_AGCY_PERS_0RAW.csv
echo   - SK_AGCY_PERS_2COL.csv
echo =======================================================================
pause
