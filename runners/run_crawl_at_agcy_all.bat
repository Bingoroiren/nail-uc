@echo off
chcp 65001 >nul
title Crawler Austria Agency (Herold + OEPD + FirmenABC + WKO)

echo =========================================================================
echo    CRAWLER SYSTEM: AUSTRIAN MANPOWER AND STAFFING AGENCIES (AT_AGCY)
echo =========================================================================
echo.

cd /d "%~dp0.."

if exist ".venv\Scripts\python.exe" (
    set "PY_CMD=.venv\Scripts\python.exe"
) else (
    set "PY_CMD=python"
)

echo [1/5] Crawling Herold.at ...
%PY_CMD% crawlmail\crawl_herold_at.py

echo.
echo [2/5] Crawling Personaldienstleister.at ...
%PY_CMD% crawlmail\crawl_personaldienstleister_at.py

echo.
echo [3/5] Crawling FirmenABC.at ...
%PY_CMD% crawlmail\crawl_firmenabc_at.py

echo.
echo [4/5] Crawling WKO.at ...
%PY_CMD% crawlmail\crawl_wko_at.py

echo.
echo [5/5] Consolidating and Formatting to 20-Column Cold Mail ...
%PY_CMD% crawlmail\consolidate_at_agcy.py

echo.
echo =========================================================================
echo    ALL SCRAPERS COMPLETED SUCCESSFULLY!
echo    Check file: AT_AGCY_COMB_2COL.csv
echo    Checklist : data\checklist_at_agcy.json
echo =========================================================================
pause
