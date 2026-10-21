@echo off
chcp 65001 >nul
title Rekvizitai Lithuania Agency Harvester and Enrichment
cd /d "%~dp0\.."

echo =======================================================================
echo   REKVIZITAI.VZ.LT - LITHUANIA EMPLOYMENT AND RECRUITMENT AGENCIES
echo   Categories: Recruitment (25 pages) + Labour Exchange (88 pages)
echo   Output: LT_AGCY_REKV_0RAW.csv, LT_AGCY_REKV_1ENR.csv, LT_AGCY_REKV_2COL.csv
echo =======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    pause
    exit /b 1
)

.venv\Scripts\python.exe csdl_mlt\harvest_rekvizitai_agcy.py

echo.
echo =======================================================================
echo   TIEN TRINH HOAN TAT HOAC DA DUOC LUU TANG DAN AN TOAN!
echo   Output files:
echo   - LT_AGCY_REKV_2COL.csv (Thu muc goc - 100%% Email len dau)
echo   - LT_AGCY_REKV_1ENR.csv (Thu muc goc - Da lam giau)
echo   - LT_AGCY_REKV_0RAW.csv (Thu muc goc - Du lieu tho)
echo   - csdl_mlt\LT_AGCY_REKV_2COL.csv
echo =======================================================================
pause
