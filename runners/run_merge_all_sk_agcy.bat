@echo off
chcp 65001 >nul
title MASTER MERGE AND DEDUPLICATION - SLOVAK EMPLOYMENT AGENCIES

echo ======================================================================
echo    GOP VA DOI CHIEU LOC TRUNG TOAN BO CSDL MOI GIOI LAO DONG SLOVAKIA
echo    NGUON: ADZC + UDZC + DNB + GREENPAGES + PERSONALNEAGENTURY
echo ======================================================================

cd /d "%~dp0\.."

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [*] Python executable: %PYTHON_EXE%
echo [*] Script thuc thi: csdl_sk_agcy\merge_all_sk_agcy.py
echo ----------------------------------------------------------------------

%PYTHON_EXE% csdl_sk_agcy\merge_all_sk_agcy.py %*

echo.
echo ======================================================================
echo    HOAN TAT GOP VA LOC TRUNG CSDL!
echo    KIEM TRA THU MUC: csdl_sk_agcy
echo    - SK_AGCY_ALL_1ENR.csv (CSDL Chi Tiet Master)
echo    - SK_AGCY_ALL_2COL.csv (Chuan 20 cot Cold Mail, 100%% Email len dau)
echo    - SK_AGCY_DEDUP_REPORT.txt (Bao Cao Doi Chieu)
echo ======================================================================
pause
