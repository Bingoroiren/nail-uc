@echo off
chcp 65001 >nul
title Scrape info.lt - Lithuania Environmental Management and Greenery

echo ===============================================================================
echo        SCRAPE INFO.LT - LITHUANIA ENVIRONMENTAL MANAGEMENT + GREENERY
echo                          (LT_ENVI)
echo ===============================================================================
echo.

cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at .venv\Scripts\python.exe!
    pause
    exit /b 1
)

echo [INFO] Running scrape_infolt_categories.py for Environmental Management...
echo.

.venv\Scripts\python.exe crawlmail\scrape_infolt_categories.py --cat envi %*
if errorlevel 1 (
    echo.
    echo [ERROR] Scraper encountered an error!
    pause
    exit /b 1
)

echo.
echo ===============================================================================
echo [SUCCESS] Lithuania Environmental Management data successfully scraped!
echo ===============================================================================
echo.
pause

