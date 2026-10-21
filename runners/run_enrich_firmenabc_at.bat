@echo off
chcp 65001 >nul
title Enrich Austria Agency via FirmenABC.at

cd /d "%~dp0.."

if exist ".venv\Scripts\python.exe" (
    set "PY_CMD=.venv\Scripts\python.exe"
) else (
    set "PY_CMD=python"
)

echo ==============================================================================
echo [START] Enriching Austrian Agency Dataset via FirmenABC.at
echo Dataset: AT_AGCY_COMB_2COL.csv
echo Features: Direct Detail URL and Smart Search + Deep Web Crawler
echo ==============================================================================

%PY_CMD% crawlmail\enrich_firmenabc_at.py

echo.
echo [COMPLETED] Enrichment finished.
pause
