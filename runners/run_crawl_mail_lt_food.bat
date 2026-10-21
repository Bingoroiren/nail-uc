@echo off
chcp 65001 >nul
title Deep Email Crawler - Lithuanian Food Processing (LT_FOOD_WEBD)
cd /d "%~dp0\.."

echo =======================================================================
echo   DEEP EMAIL CRAWLER - LITHUANIAN FOOD PROCESSING ENTERPRISES
echo   Dataset: LT_FOOD_WEBD_1ENR.csv + LT_FOOD_WEBD_2COL.csv
echo   Method: Priority 10 DOM Menu + Baltic Subpaths + CF Decode + B2B Scoring
echo =======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    echo Please install Python virtual environment first.
    pause
    exit /b 1
)

echo [1/2] Checking target file LT_FOOD_WEBD_1ENR.csv...
if not exist "LT_FOOD_WEBD_1ENR.csv" (
    echo [ERROR] LT_FOOD_WEBD_1ENR.csv does not exist!
    pause
    exit /b 1
)

echo [2/2] Launching Deep Email Crawler (Multi-threaded curl_cffi)...
echo Auto-saves checkpoints every 10 companies to cache and CSV.
echo.
.venv\Scripts\python.exe crawlmail\crawl_mail_lt_food.py

echo.
echo =======================================================================
echo   CRAWLING COMPLETED OR STOPPED SAFELY
echo   Data saved to:
echo     - LT_FOOD_WEBD_1ENR.csv (Full enriched dataset)
echo     - LT_FOOD_WEBD_2COL.csv (Standard 20-col Cold Mail, 100%% emails on top)
echo =======================================================================
pause
