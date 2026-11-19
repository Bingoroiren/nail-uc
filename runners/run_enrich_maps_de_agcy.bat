@echo off
chcp 65001 >nul
title Lam Giau Du Lieu Duc Bang Google Maps (DE_AGCY_WEBD)

echo ======================================================================
echo   HE THONG LAM GIAU DU LIEU VIEC LAM VA ZEITARBEIT DUC (DE_AGCY_WEBD)
echo   TIM KIEM GOOGLE MAPS + SMART NAME MATCHING + BOC TACH EMAIL B2B
echo   Tuan thu: GEMINI.md (Rule 1, 2, 3, 4, 5, 8, 9, 10, 11, 12)
echo ======================================================================
echo.

cd /d "%~dp0\.."

set "PYTHON_EXE=.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=python"
)

echo [*] Python executable: %PYTHON_EXE%
echo [*] Script thuc thi: crawlmail\enrich_maps_de_agcy.py
echo [*] Che do mo Chrome truc quan (headless=False) theo doi tien do...
echo ----------------------------------------------------------------------
echo.

"%PYTHON_EXE%" crawlmail\enrich_maps_de_agcy.py %*

echo.
echo ======================================================================
echo   TIEN TRINH LAM GIAU HOAN TAT!
echo   Vui long kiem tra cac file dau ra:
echo   1. DE_AGCY_WEBD_1ENR.csv (CSDL da lam giau)
echo   2. DE_AGCY_WEBD_2COL.csv (Cold Mail 20 cot, 100%% email len dau)
echo   3. DE_AGCY_WEBD_ONLY_EMAILS_READY.csv (Chi chua DN co email)
echo   4. DE_AGCY_WEBD_0RAW.csv (Cap nhat file thô)
echo ======================================================================
pause
