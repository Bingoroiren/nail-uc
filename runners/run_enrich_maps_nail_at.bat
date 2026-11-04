@echo off
chcp 65001 >nul
title Google Maps Data Enrichment for Austria Nail Salons
cd /d "%~dp0\.."

echo ======================================================================
echo    GOOGLE MAPS ENRICHMENT FOR AUSTRIA NAIL SALONS
echo    Target: AT_NAIL_ALL_2COL.csv
echo    Scope: Enrich 2,395 nail salons without email via Google Maps
echo           Extract official websites, phones, and deep crawl /impressum
echo ======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment python.exe not found at .venv\Scripts\python.exe!
    pause
    exit /b 1
)

echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [*] Starting Google Maps enrichment...
echo.

python -u crawlmail\enrich_maps_nail_at.py %*
if errorlevel 1 goto RunFailed

echo.
echo ======================================================================
echo [SUCCESS] Google Maps enrichment completed successfully!
echo Files updated:
echo  - AT_NAIL_ALL_ONLY_EMAILS_READY.csv
echo  - AT_NAIL_ALL_2COL.csv
echo  - csdl_mlt\AT_NAIL_ALL_ONLY_EMAILS_READY.csv
echo  - archive\at_austria\AT_NAIL_ALL_ONLY_EMAILS_READY.csv
echo ======================================================================
echo.
pause
goto End

:RunFailed
echo.
echo [ERROR] Enrichment process encountered an error!
pause
exit /b 1

:End

