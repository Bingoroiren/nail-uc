@echo off
title Slovakia Metal Production Directory Crawler
cd /d "%~dp0.."

echo ======================================================
echo    SLOVAKIA METAL PRODUCTION DIRECTORIES CRAWLER
echo    Sources: instituciafiriem, profesionalnyregister, europskefirmy
echo    Output: SK_MTAL_ISEU_0RAW.csv
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
echo STEP 1: Launching Crawler and Deduplication...
echo ======================================================
python -u crawlmail/crawl_sk_metal_iseu.py
if errorlevel 1 goto RunFailed

echo.
echo ======================================================
echo    CRAWL AND DEDUPLICATION COMPLETED SUCCESSFULLY!
echo    Output file: SK_MTAL_ISEU_0RAW.csv
echo ======================================================
pause
goto End

:NoPython
echo [ERROR] Python is not installed or not in your PATH.
pause
exit /b

:RunFailed
echo [ERROR] Crawl failed during execution.
pause
exit /b

:End
