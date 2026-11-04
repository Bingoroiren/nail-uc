@echo off
chcp 65001 >nul
title Scrape info.lt - Lithuania Welding Equipment

echo ===============================================================================
echo        SCRAPE INFO.LT - LITHUANIA WELDING EQUIPMENT
echo                          (LT_WELD)
echo ===============================================================================
echo.

cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at .venv\Scripts\python.exe!
    pause
    exit /b 1
)

echo [INFO] Running scrape_infolt_categories.py for Welding Equipment...
echo.

.venv\Scripts\python.exe crawlmail\scrape_infolt_categories.py --cat weld %*
if errorlevel 1 (
    echo.
    echo [ERROR] Scraper encountered an error!
    pause
    exit /b 1
)

echo.
echo ===============================================================================
echo [SUCCESS] Lithuania Welding Equipment data successfully scraped!
echo ===============================================================================
echo.
pause

