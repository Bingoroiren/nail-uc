@echo off
chcp 65001 >nul
title Filter Mail Tracker and Bounce - LT Food CleanData

echo ========================================================
echo   FILTER MAIL TRACKER AND BOUNCE - LT FOOD CLEANDATA
echo   Target: (xong 10_18) LT_FOOD_WEBS - CleanData.csv
echo   Tracker: Mail Tracker - mail.csv
echo   Output: Cleaned CleanData + Audit Log
echo ========================================================
echo.

cd /d "%~dp0\.."

if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Starting Filter and Deduplication...
%PYTHON_EXE% crawlmail\filter_tracker_lt_food.py

echo.
echo Process completed!
pause

