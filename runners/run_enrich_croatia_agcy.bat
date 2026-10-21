@echo off
chcp 65001 >nul
title CROATIA EMPLOYMENT AGENCIES ENRICHMENT PIPELINE (HR_AGCY)

cd /d "%~dp0\.."

echo ============================================================
echo   CROATIA EMPLOYMENT AGENCIES ENRICHMENT PIPELINE (HR_AGCY)
echo   Sources: FinInfo.hr + Tvrtke.hr + Website Deep Crawl
echo ============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Python virtual environment not found in .venv!
    pause
    exit /b 1
)

.venv\Scripts\python.exe crawlmail\enrich_croatia_agcy.py

echo.
echo ============================================================
echo   Enrichment process finished!
echo ============================================================
pause
