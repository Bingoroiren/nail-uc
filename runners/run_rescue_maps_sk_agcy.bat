@echo off
chcp 65001 >nul
title RESCUE PASS - SLOVAK EMPLOYMENT AGENCIES (SMART MATCH)

echo ======================================================================
echo     KHOI DONG VONG CUU HO GOOGLE MAPS VA QUET EMAIL B2B (SLOVAKIA AGCY)
echo     AP DUNG SMART NAME MATCHING (UNICODE NFKD + BRACKET STRIPPING)
echo ======================================================================

cd /d "%~dp0\.."

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [*] Python executable: %PYTHON_EXE%
echo [*] Script thuc thi: crawlmail\rescue_maps_sk_agcy.py
echo [*] Che do mo Chrome truc quan theo doi tien do thuc te...
echo ----------------------------------------------------------------------

%PYTHON_EXE% crawlmail\rescue_maps_sk_agcy.py %*

echo.
echo ======================================================================
echo    HOAN TAT CUU HO DU LIEU!
echo    KIEM TRA THU MUC: csdl_sk_agcy
echo    - SK_AGCY_DNB_1ENR.csv (CSDL Chi Tiet)
echo    - SK_AGCY_DNB_2COL.csv (Chuan 20 cot Cold Mail, 100%% Email len dau)
echo ======================================================================
pause
