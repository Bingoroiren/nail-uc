@echo off
chcp 65001 >nul
title Scrape Info.lt Wood and Furniture - Lithuania
cd /d "%~dp0\.."

echo ========================================================
echo   SCRAPER INFO.LT - WOOD AND FURNITURE LITHUANIA
echo   Categories:
echo     1. Baldu gamyba (Furniture Manufacturing)
echo     2. Medienos apdirbimas (Wood Processing)
echo   Output:
echo     - LT_WOOD_INLT_0RAW.csv
echo     - LT_WOOD_INLT_2COL.csv
echo     - LT_WOOD_INLT_ONLY_EMAILS_READY.csv
echo ========================================================
echo.

if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Starting crawler for Info.lt Wood and Furniture...
%PYTHON_EXE% -u crawlmail\scrape_infolt_wood.py --workers 8 %*
if errorlevel 1 goto RunFailed

echo.
echo ========================================================
echo [SUCCESS] Info.lt Wood and Furniture scraper completed!
echo ========================================================
echo.
pause
goto End

:RunFailed
echo.
echo [ERROR] Scraper encountered an error!
pause
exit /b 1

:End

