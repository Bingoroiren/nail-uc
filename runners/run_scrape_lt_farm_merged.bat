@echo off
chcp 65001 >nul
title Thu thap va Hop nhat Nong Nghiep Litva (LT_FARM_WEBD)

echo ======================================================================
echo   HE THONG THU THAP VA HOP NHAT NONG NGHIEP LITVA (LT_FARM_WEBD)
echo   Nguon: Fermos.lt (Top 100) + Firmavis.com (NACE 01, 02)
echo   Tuan thu: GEMINI.md (Rule 1, 2, 3, 5, 6, 8, 10, 12)
echo ======================================================================
echo.

cd /d "%~dp0\.."

set "PYTHON_EXE=.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=python"
)

echo [*] Dang khoi chay tien trinh hop nhat du lieu...
"%PYTHON_EXE%" crawlmail\scrape_lt_farm_merged.py

echo.
echo ======================================================================
echo   TIEN TRINH DA HOAN TAT!
echo   Vui long kiem tra cac file dau ra:
echo   1. LT_FARM_WEBD_0RAW.csv
echo   2. LT_FARM_WEBD_2COL.csv
echo   3. LT_FARM_WEBD_ONLY_EMAILS_READY.csv
echo ======================================================================
pause
