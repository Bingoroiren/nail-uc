@echo off
title Austria Agency Playwright Deep Email Recrawler
cd /d "%~dp0.."

echo ======================================================
echo    AUSTRIA AGENCY DEEP EMAIL RE-CRAWLER (RESET MODE)
echo    Target: AT_AGCY_SHET_1ENR.csv
echo    Engine: Playwright Chromium (Full JS and DOM Engine)
echo    Mode: --retry-empty (Recrawls all missing emails)
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

echo [*] Checking Playwright Chromium...
playwright install chromium >nul 2>&1

echo.
echo ======================================================
echo STEP 1: Launching Playwright Deep Email Recrawler...
echo ======================================================
python -u crawlmail/recrawl_empty_emails_at_agcy.py --retry-empty
if errorlevel 1 goto RunFailed

echo.
echo ======================================================
echo    RE-CRAWL COMPLETED SUCCESSFULLY!
echo    Output file: AT_AGCY_SHET_1ENR.csv
echo ======================================================
pause
goto End

:NoPython
echo [ERROR] Python is not installed or not in your PATH.
pause
exit /b

:RunFailed
echo [ERROR] Recrawl failed during execution.
pause
exit /b

:End
