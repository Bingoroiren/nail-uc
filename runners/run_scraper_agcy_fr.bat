@echo off
chcp 65001 >nul
title Google Maps Scraper - France Recruitment and Interim Agencies (FR_AGCY_GMAP)

cd /d "%~dp0\.."

echo ======================================================================
echo    GOOGLE MAPS SCRAPER - FRANCE RECRUITMENT AND INTERIM AGENCIES
echo    Output: FR_AGCY_GMAP_0RAW.csv
echo ======================================================================
echo.

.venv\Scripts\python.exe src\scraper_agcy_fr.py

echo.
echo ======================================================================
echo    COMPLETED
echo ======================================================================
pause

