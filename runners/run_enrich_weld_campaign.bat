@echo off
chcp 65001 >nul
title Shipyard Welder Agencies and Contractors Enrichment - KR_WELD_COMB

echo ======================================================================
echo  CHIEN DICH LAM GIAU DU LIEU: MOI GIOI VA THAU PHU THO HAN DONG TAU E-7-3
echo  Tap du lieu: KR_WELD_COMB_0RAW.csv (936 doanh nghiep thu phu dong tau)
echo  Co che: Tu dong ghi luu tang dan cu moi 5 co so va Resume 100%%
echo ======================================================================
echo.

cd /d "%~dp0\.."

set PYTHON_EXE=C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe
if not exist "%PYTHON_EXE%" (
    set PYTHON_EXE=python
)

set NUM_ITEMS=%1
if "%NUM_ITEMS%"=="" set NUM_ITEMS=0

echo [1/2] Dang khoi chay Chromium truc quan (headless=False)...
echo [2/2] Dang tra cuu Google Maps va Website de boc tach Email, SDT tho han...
echo.

"%PYTHON_EXE%" -u crawlmail\enrich_maps_kr_weld.py %NUM_ITEMS%

echo.
echo ======================================================================
echo  HOAN TAT CHIEN DICH QUET LAM GIAU DU LIEU!
echo  Ket qua duoc luu truc tiep vao:
echo   - KR_WELD_COMB_1ENR.csv
echo   - KR_WELD_COMB_2COL.csv (Chuan Cold Mail 20 cot, Email len dau)
echo ======================================================================
pause
