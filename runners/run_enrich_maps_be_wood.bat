@echo off
chcp 65001 >nul
title Google Maps and Email Enrichment - Belgium Wood Enterprises
cd /d "%~dp0\.."

echo ========================================================
echo   GOOGLE MAPS AND B2B EMAIL ENRICHMENT - BELGIUM WOOD
echo   Input: BE_WOOD_KBO0_0RAW.csv
echo   Output 1: BE_WOOD_GMAP_1ENR.csv
echo   Output 2: BE_WOOD_GMAP_2COL.csv (20 Standard Columns)
echo   Rule 1: CSV UTF-8 with BOM (utf-8-sig)
echo   Rule 2: Phone with single quote '+32...
echo   Rule 3: Single best B2B email, emails sorted to top
echo   Rule 4: Visual browser mode (headless=False)
echo   Rule 10: Fixed 17-character file names
echo   Rule 12: Permanent Blacklist Excluded
echo ========================================================
echo.

if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Starting Google Maps and Email Enrichment for Belgium Wood...
%PYTHON_EXE% -u crawlmail\enrich_maps_be_wood.py %*
if errorlevel 1 goto RunFailed

echo.
echo ========================================================
echo [SUCCESS] Maps and Email Enrichment completed!
echo Ready Cold Mail files saved:
echo  - BE_WOOD_GMAP_1ENR.csv
echo  - BE_WOOD_GMAP_2COL.csv
echo  - csdl_mlt\BE_WOOD_GMAP_2COL.csv
echo  - archive\be_belgium\BE_WOOD_GMAP_2COL.csv
echo ========================================================
echo.
pause
goto End

:RunFailed
echo.
echo [ERROR] Enrichment process encountered an error!
pause
exit /b 1

:End

