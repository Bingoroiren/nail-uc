@echo off
chcp 65001 >nul
title Cao Sau Website and Email (KR_AGCY_SHIP_2COL)
cd /d "%~dp0\.."

echo ========================================================
echo   CAO SAU WEBSITE + EMAIL + SDT (NAVER SEARCH + BLOGS)
echo ========================================================
echo.

if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe crawlmail\deep_enrich_search.py
) else (
    python crawlmail\deep_enrich_search.py
)

echo.
echo ========================================================
echo   HOAN TAT QUET SAU DU LIEU
echo ========================================================
pause
