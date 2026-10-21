@echo off
title Austria Agency Missing Websites and Email Enrichment
cd /d "%~dp0.."

echo ======================================================
echo    AUSTRIA AGENCY MISSING WEBSITES AND EMAIL ENRICHMENT
echo    Target: AT_AGCY_SHET_1ENR.csv
echo    Mode:   Strict Name Matching and WKO Verification
echo    Goal:   Enrich 1061 companies without website
echo ======================================================

python --version >nul 2>&1
if errorlevel 1 goto NoPython

if exist .venv goto ActivateVenv
echo [*] Error: Virtual environment .venv not found.
pause
exit /b

:ActivateVenv
echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

echo.
echo ======================================================
echo STEP 1: Launching Strict Search and Enrichment...
echo ======================================================
python -u crawlmail/enrich_missing_websites_at_agcy.py
if errorlevel 1 goto RunFailed

echo.
echo ======================================================
echo STEP 2: Updating Cold Mail 20 Columns...
echo ======================================================
python -u formatters/format_at_agcy_shet.py
if errorlevel 1 goto RunFailed

echo.
echo ======================================================
echo    ENRICHMENT AND COLD MAIL FORMATTING COMPLETED!
echo    Output: AT_AGCY_SHET_2COL.csv
echo ======================================================
pause
goto End

:NoPython
echo [ERROR] Python is not installed or not in your PATH.
pause
exit /b

:RunFailed
echo [ERROR] Enrichment failed during execution.
pause
exit /b

:End
