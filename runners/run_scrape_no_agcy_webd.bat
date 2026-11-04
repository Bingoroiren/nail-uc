@echo off
chcp 65001 >nul
title Scrape Norway HR Agencies - Proff and Gulesider

echo ========================================================
echo   SCRAPE NORWAY RECRUITMENT AND STAFFING AGENCIES
echo   Sources: Proff.no + Gulesider.no
echo   Output: NO_AGCY_WEBD_0RAW.csv (17-char format)
echo ========================================================
echo.

cd /d "%~dp0\.."

if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Starting Scraper...
%PYTHON_EXE% crawlmail\scraper_no_agcy_webd.py

echo.
echo Process completed!
pause

