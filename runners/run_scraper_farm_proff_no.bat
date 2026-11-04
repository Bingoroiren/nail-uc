@echo off
chcp 65001 >nul
cd /d "%~dp0\.."

echo ======================================================================
echo  SCRAPER AND ENRICHMENT - NORWAY AGRICULTURE AND LIVESTOCK (PROFF.NO)
echo ======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment python.exe not found!
    pause
    exit /b 1
)

echo Starting Proff.no scraper for Norway Agriculture and Livestock...
echo - Filtering out museums, schools, social entities
echo - Keeping only crop farming and livestock
echo - Auto-enriching emails from websites
echo - Saving incrementally to NO_FARM_WEBD_0RAW.csv and NO_FARM_WEBD_2COL.csv
echo.

.venv\Scripts\python.exe crawlmail\scraper_farm_proff_no.py %*

echo.
echo Process completed!
pause

