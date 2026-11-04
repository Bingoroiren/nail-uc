@echo off
chcp 65001 >nul
title KBO Belgium Metal Fabrication Scraper
cd /d "%~dp0\.."

echo ========================================================
echo   KBO BELGIUM METAL FABRICATION AND MACHINING SCRAPER
echo   Codes (NACE): 25110, 25120, 25210, 25220, 25401,
echo                 25530, 25610, 25620, 2563, 25910
echo   Covers: 100 percent metal subcodes (incl 25631, 25639)
echo   Mode: Visual Browser (headless=False) with AI OCR Captcha
echo   Source: KBO Public Search (Official Belgian Registry)
echo   Output: BE_METL_KBO0_0RAW.csv (Rule 10: 17 characters)
echo   Postcodes: 1187 Belgian Postcodes
echo   Permanent Blacklist: Excluded Automatically
echo ========================================================
echo.

if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Starting KBO Belgium Metal Scraper across all Belgian postcodes...
%PYTHON_EXE% -u src\scraper_be_metal_kbo.py %*
if errorlevel 1 goto RunFailed

echo.
echo ========================================================
echo [SUCCESS] Scraping completed successfully!
echo Output saved to:
echo  - BE_METL_KBO0_0RAW.csv
echo  - csdl_mlt\BE_METL_KBO0_0RAW.csv
echo  - archive\be_belgium\BE_METL_KBO0_0RAW.csv
echo ========================================================
echo.
pause
goto End

:RunFailed
echo.
echo [ERROR] Scraper encountered an error!
pause
exit /b 1

:End

