@echo off
chcp 65001 >nul
title Harvest PagesJaunes Paris - Native Google Chrome CDP Mode

cd /d "%~dp0\.."

echo ======================================================================
echo    PAGESJAUNES PARIS HARVESTER (NATIVE GOOGLE CHROME CDP MODE)
echo    Inherited from Lithuania Rekvizitai anti-Turnstile architecture
echo    Target 1: Recrutement international (Paris 75000)
echo    Target 2: Agences d'interim (Paris 75000)
echo    Output:   FR_AGCY_PJAU_0RAW.csv
echo ======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    pause
    exit /b 1
)

.venv\Scripts\python.exe crawlmail\harvest_pagesjaunes_paris.py

echo.
echo ======================================================================
echo    HARVEST COMPLETED
echo ======================================================================
pause

