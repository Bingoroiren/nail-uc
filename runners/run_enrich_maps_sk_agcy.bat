@echo off
chcp 65001 >nul
title GOOGLE MAPS ENRICHMENT - SLOVAK EMPLOYMENT AGENCIES

echo ======================================================================
echo    KHOI DONG HE THONG LAM GIAU DU LIEU GOOGLE MAPS VA QUET EMAIL B2B
echo          CSDL NGANH MOI GIOI LAO DONG SLOVAKIA (1000 CONG TY)
echo ======================================================================

cd /d "%~dp0\.."

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [*] Su dung moi truong Python: %PYTHON_EXE%
echo [*] Script thuc thi: crawlmail\enrich_maps_sk_agcy.py
echo [*] Che do mo trinh duyet truc quan de theo doi tien do thuc te...
echo ----------------------------------------------------------------------

%PYTHON_EXE% crawlmail\enrich_maps_sk_agcy.py %*

echo.
echo ======================================================================
echo    HOAN TAT TAC VU LAM GIAU DU LIEU!
echo    KIEM TRA THU MUC: csdl_sk_agcy
echo    - SK_AGCY_DNB_1ENR.csv (CSDL Chi Tiet)
echo    - SK_AGCY_DNB_2COL.csv (Chuan 20 cot Cold Mail, 100%% Email len dau)
echo ======================================================================
pause
