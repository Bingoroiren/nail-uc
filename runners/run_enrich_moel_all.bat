@echo off
chcp 65001 >nul
title Progressive Full Enrichment - KR_AGCY_MOEL (ALL ITEMS)

echo ======================================================================
echo  LAM GIAU DU LIEU TOAN BO 100%% (ALL ITEMS - KHONG DUNG CHO DEN KHI XONG)
echo  Tap du lieu: KR_AGCY_MOEL_0RAW.csv
echo  Co che: Tu dong ghi luu tang dan cu moi 5 co so va Resume 100%%
echo ======================================================================
echo.

cd /d "%~dp0\.."

set PYTHON_EXE=C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe
if not exist "%PYTHON_EXE%" (
    set PYTHON_EXE=python
)

echo [1/2] Dang khoi chay Chromium truc quan (headless=False)...
echo [2/2] Dang tra cuu danh ba Bizno, Google Maps va Website de lay Email, SDT...
echo.

"%PYTHON_EXE%" -u crawlmail\enrich_moel_directories.py 0

echo.
echo ======================================================================
echo  HOAN TAT 100%% TOAN BO TAP DU LIEU!
echo  Ket qua duoc luu truc tiep vao:
echo   - KR_AGCY_MOEL_0RAW.csv
echo ======================================================================
pause
