@echo off
chcp 65001 >nul
title Google Maps and Email Enrichment - KR_SHIP_HIPC (HD Hyundai + KOSIC)

echo ======================================================================
echo  LAM GIAU DU LIEU GOOGLE MAPS VA EMAIL - NGANH DONG TAU HAN QUOC
echo  Tap du lieu: KR_SHIP_HIPC_0RAW.csv (183 Doanh nghiep thau phu va xuong tau)
echo ======================================================================
echo.

cd /d "%~dp0\.."

set PYTHON_EXE=C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe
if not exist "%PYTHON_EXE%" (
    set PYTHON_EXE=python
)

echo [1/2] Dang khoi chay Playwright Chromium truc quan (headless=False)...
echo [2/2] Dang tra cuu Google Maps va boc tach Email B2B...
echo.

"%PYTHON_EXE%" crawlmail\enrich_maps_hipc.py

echo.
echo ======================================================================
echo  HOAN TAT LAM GIAU DU LIEU CHO KR_SHIP_HIPC!
echo  Tep ket qua:
echo   - KR_SHIP_HIPC_1ENR.csv (Ban day du thong tin lam giau)
echo   - KR_SHIP_HIPC_2COL.csv (Ban Cold Mail 20 cot, day email len dau)
echo ======================================================================
pause
