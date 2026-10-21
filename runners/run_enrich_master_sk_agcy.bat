@echo off
chcp 65001 >nul
title MASTER ENRICHMENT - SLOVAKIA EMPLOYMENT AGENCIES

echo ======================================================================
echo    HE THONG LAM GIAU DU LIEU DA TANG - AGCY SLOVAKIA (CHONG CHAN BOT)
echo    DA TANG: ZLATE STRANKY + GOOGLE MAPS SMART + DEEP WEB CRAWLER
echo ======================================================================

cd /d "%~dp0\.."

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [*] Python interpreter: %PYTHON_EXE%
echo [*] Target dataset    : SK_AGCY_ALL_2COL.csv (3,845 companies)
echo [*] Script executor   : crawlmail\enrich_master_sk_agcy.py
echo [*] Running Chrome in interactive visual mode (headless=False)
echo ----------------------------------------------------------------------

%PYTHON_EXE% crawlmail\enrich_master_sk_agcy.py %*

echo.
echo ======================================================================
echo    TIEN TRINH HOAN TAT HOAC DA TAM DUNG AN TOAN!
echo    DU LIEU DA DUOC LUU TANG DAN VAO CAC TEP:
echo    - SK_AGCY_ALL_2COL.csv (Thu muc goc - 100%% Email len dau)
echo    - csdl_sk_agcy\SK_AGCY_ALL_2COL.csv
echo    - csdl_sk_agcy\SK_AGCY_ALL_1ENR.csv
echo ======================================================================
pause
