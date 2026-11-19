@echo off
chcp 65001 >nul
title Lam Giau Du Lieu Google Maps - Nong Nghiep Litva (LT_FARM_GMAP)

echo ======================================================================
echo   HE THONG LAM GIAU DU LIEU GOOGLE MAPS - NONG NGHIEP LITVA
echo   Tuan thu nghiem ngat GEMINI.md (Rule 1, 2, 3, 4, 5, 8, 10, 11, 12)
echo ======================================================================
echo.

cd /d "%~dp0\.."

set "PYTHON_EXE=.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=python"
)

echo [*] Che do trinh duyet truc quan (headless=False) de theo doi va xu ly Captcha...
echo [*] Dang khoi chay tien trinh lam giau du lieu Google Maps...
echo.

"%PYTHON_EXE%" crawlmail\enrich_maps_lt_farm.py %*

echo.
echo ======================================================================
echo   TIEN TRINH DA HOAN TAT!
echo   Vui long kiem tra cac file dau ra:
echo   1. LT_FARM_GMAP_1ENR.csv
echo   2. LT_FARM_GMAP_2COL.csv
echo   3. LT_FARM_GMAP_ONLY_EMAILS_READY.csv
echo ======================================================================
pause
