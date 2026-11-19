@echo off
chcp 65001 >nul
title Scrape PagesJaunes Paris - Recruitment and Interim (FR_AGCY_PJAU)

cd /d "%~dp0\.."

echo ======================================================================
echo    PAGESJAUNES PARIS SCRAPER - RECRUITMENT AND INTERIM AGENCIES
echo    Target 1: Recrutement international (Paris 75000)
echo    Target 2: Agences d'interim (Paris 75000)
echo    Output:   FR_AGCY_PJAU_0RAW.csv
echo ======================================================================
echo.

.venv\Scripts\python.exe crawlmail\scraper_pagesjaunes.py

echo.
echo ======================================================================
echo    COMPLETED
echo ======================================================================
pause

