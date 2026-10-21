@echo off
chcp 65001 >nul
title Progressive Directory and Web Enrichment - KR_AGCY_MOEL

echo ======================================================================
echo  LAM GIAU DU LIEU TU DONG TU CAC TRANG DANH BA DOANH NGHIEP (BIZNO/GGMAP)
echo  Tap du lieu: KR_AGCY_MOEL_0RAW.csv (Cac van phong viec lam ven bien)
echo ======================================================================
echo.

cd /d "%~dp0\.."

set PYTHON_EXE=C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe
if not exist "%PYTHON_EXE%" (
    set PYTHON_EXE=python
)

echo [1/2] Dang khoi chay Chromium truc quan (headless=False)...
echo [2/2] Dang tra cuu danh ba Bizno, Google Maps va boc tach Email/SDT...
echo.

set NUM_ITEMS=%1
if "%NUM_ITEMS%"=="" set NUM_ITEMS=0

"%PYTHON_EXE%" -u crawlmail\enrich_moel_directories.py %NUM_ITEMS%

echo.
echo ======================================================================
echo  HOAN TAT DOT QUET LAM GIAU DU LIEU!
echo  Ket qua duoc luu tang dan truc tiep vao:
echo   - KR_AGCY_MOEL_0RAW.csv
echo ======================================================================
pause
