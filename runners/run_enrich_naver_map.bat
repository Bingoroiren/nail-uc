@echo off
chcp 65001 >nul
title Lam Giau Du Lieu Naver Map (KR_AGCY_SHIP_2COL)
cd /d "%~dp0\.."

echo ========================================================
echo   LAM GIAU DANH SACH THO QUA NAVER MAP (SĐT + WEBSITE)
echo ========================================================
echo.

if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe crawlmail\enrich_raw_naver_map.py
) else (
    python crawlmail\enrich_raw_naver_map.py
)

echo.
echo ========================================================
echo   HOAN TAT LAM GIAU DU LIEU NAVER MAP
echo ========================================================
pause
