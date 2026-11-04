@echo off
chcp 65001 >nul
title Scrape info.lt - All Categories (Welding and Environmental)

echo ===============================================================================
echo        SCRAPE INFO.LT - ALL CATEGORIES (WELDING + ENVIRONMENTAL)
echo                    (LT_WELD and LT_ENVI)
echo ===============================================================================
echo.

cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at .venv\Scripts\python.exe!
    pause
    exit /b 1
)

echo [INFO] Running scrape_infolt_categories.py for both categories...
echo.

.venv\Scripts\python.exe crawlmail\scrape_infolt_categories.py --cat all %*
if errorlevel 1 (
    echo.
    echo [ERROR] Scraper encountered an error!
    pause
    exit /b 1
)

echo.
echo ===============================================================================
echo [SUCCESS] Both Lithuania categories successfully scraped!
echo ===============================================================================
echo.
pause

