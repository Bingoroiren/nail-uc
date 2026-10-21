@echo off
chcp 65001 >nul
title Google Maps and Web Enrichment - Austrian Agencies (AT_AGCY)
cd /d "%~dp0.."

echo =========================================================================
echo    GOOGLE MAPS AND DEEP WEB ENRICHMENT: AUSTRIAN AGENCIES (AT_AGCY)
echo    Target: AT_AGCY_COMB_2COL.csv (3,752 companies)
echo    Outputs:
echo      - AT_AGCY_COMB_2COL.csv (Direct update, emails sorted to top)
echo      - data/AT_AGCY_COMB_2COL.csv (Sync backup)
echo      - AT_AGCY_GMAP_2COL.csv (17-character standardized name)
echo    Engine: Google Maps (Playwright UI) + Deep Web Multi-tier Scraper
echo =========================================================================
echo.

:: 1. Check Python
if exist ".venv\Scripts\python.exe" (
    set "PY_CMD=.venv\Scripts\python.exe"
    goto RunScript
)

python --version >nul 2>&1
if errorlevel 1 goto NoPython
set "PY_CMD=python"

:RunScript
echo [*] Checking dependencies...
%PY_CMD% -c "import playwright, bs4" >nul 2>&1
if errorlevel 1 (
    echo [*] Installing requirements...
    %PY_CMD% -m pip install -r requirements.txt >nul 2>&1
    playwright install chromium >nul 2>&1
)

echo.
echo =========================================================================
echo    LAUNCHING ENRICHMENT PIPELINE...
echo    (Chrome window will open for visual progress monitoring and captcha)
echo =========================================================================
echo.

%PY_CMD% -u crawlmail/enrich_maps_at_agcy.py
if errorlevel 1 goto RunFailed

echo.
echo =========================================================================
echo    ENRICHMENT COMPLETED SUCCESSFULLY!
echo    Emails prioritized and saved to:
echo      - AT_AGCY_COMB_2COL.csv
echo      - AT_AGCY_GMAP_2COL.csv
echo =========================================================================
pause
goto End

:NoPython
echo [-] Error: Python is not installed or not in PATH!
pause
exit /b 1

:RunFailed
echo.
echo [-] Enrichment script encountered an error or was stopped.
pause
exit /b 1

:End
