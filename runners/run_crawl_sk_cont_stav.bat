@echo off
title Slovakia Construction Companies Crawler (Stavbari)
cd /d "%~dp0.."

echo ======================================================
echo    SLOVAKIA CONSTRUCTION DIRECTORY CRAWLER (STAVBARI)
echo    Target: SK_CONT_STAV_0RAW.csv
echo    Source: https://stavbari.profesionalnyregister.sk/#this
echo    Filter: Exclude non-construction (dentists, medical, spa, etc.)
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
echo STEP 1: Launching Crawler and Classifier...
echo ======================================================
python -u crawlmail/crawl_sk_cont_stav.py
if errorlevel 1 goto RunFailed

echo.
echo ======================================================
echo    CRAWL AND CLASSIFICATION COMPLETED!
echo    Output file: SK_CONT_STAV_0RAW.csv
echo ======================================================
pause
goto End

:NoPython
echo [ERROR] Python is not installed or not in your PATH.
pause
exit /b

:RunFailed
echo [ERROR] Crawling failed during execution.
pause
exit /b

:End
