@echo off
chcp 65001 >nul
title Cross-reference and Enrich Austria Agencies with CleanData
cd /d "%~dp0.."

echo =========================================================================
echo    CROSS-REFERENCE AND ENRICH: AUSTRIAN AGENCIES WITH CLEANDATA
echo    Source   : AT_AGCY_COMB_2COL.csv
echo    Reference: AT_AGCY_WKOS - CleanData.csv
echo    Actions  :
echo      1. Remove 100%% of companies that have already replied
echo      2. Clean out known bounced emails
echo      3. Enrich missing Emails, Phones, Addresses
echo      4. Sort with 100%% of emails at the top
echo =========================================================================
echo.

if exist ".venv\Scripts\python.exe" (
    set "PY_CMD=.venv\Scripts\python.exe"
) else (
    set "PY_CMD=python"
)

%PY_CMD% crawlmail\cross_enrich_at_agcy_clean.py
if errorlevel 1 (
    echo.
    echo [-] Error occurred during cross-enrichment.
    pause
    exit /b 1
)

echo.
echo =========================================================================
echo    PROCESS COMPLETED SUCCESSFULLY!
echo    Outputs:
echo      - AT_AGCY_COMB_2COL.csv
echo      - AT_AGCY_GMAP_2COL.csv
echo      - data/AT_AGCY_REPLIED_REMOVED.csv
echo =========================================================================
pause
