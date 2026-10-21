@echo off
chcp 65001 >nul
title Crawl SlovakData NACE 28, 29, 25

cd /d "%~dp0\.."

echo =======================================================
echo   CRAWL SLOVAKDATA.SK NACE CODES 28, 29, 25
echo   Output files:
echo   - SK_MECH_SLVD_0RAW.csv (NACE 28: Machinery)
echo   - SK_AUTO_SLVD_0RAW.csv (NACE 29: Automotive)
echo   - SK_MTAL_SLVD_0RAW.csv (NACE 25: Fabricated Metal)
echo =======================================================

.venv\Scripts\python.exe crawlmail\crawl_slovakdata_nace.py all

echo.
echo =======================================================
echo   CRAWL COMPLETED SUCCESSFULLY!
echo =======================================================
pause
