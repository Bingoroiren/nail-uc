@echo off
chcp 65001 >nul
title TEST Enrich Korean Shipping Companies via Naver and Deep Web
cd /d "%~dp0\.."

echo ======================================================
echo    TEST MODE: ENRICH 10 COMPANIES VIA NAVER AND DEEP WEB
echo ======================================================

set PYTHON_CMD=python
if exist ".venv\Scripts\python.exe" (
    set PYTHON_CMD=.venv\Scripts\python.exe
)

%PYTHON_CMD% crawlmail\enrich_kr_ship_naver.py --test 10

echo.
echo ======================================================
echo    TEST COMPLETED! CHECK OUTPUT FILES:
echo    - KR_SHIP_NAVR_1ENR.csv
echo    - KR_SHIP_NAVR_2COL.csv
echo ======================================================
pause
