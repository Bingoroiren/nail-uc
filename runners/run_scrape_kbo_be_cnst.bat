@echo off
chcp 65001 >nul
title KBO Belgium Construction Scraper
cd /d "%~dp0\.."

echo ========================================================
echo   KBO BELGIUM CONSTRUCTION ENTERPRISES SCRAPER
echo   Codes (NACE): 43110, 43120, 43230, 43310, 43320,
echo                 4333, 4334, 43410, 4342, 43910
echo   Covers: 100 percent of requested 14 construction codes
echo   Mode: Visual Browser (headless=False) with AI OCR Captcha
echo   Source: KBO Public Search (Official Belgian Registry)
echo   Output: BE_CNST_KBO0_0RAW.csv (Rule 10: 17 characters)
echo   Postcodes: 1187 Belgian Postcodes
echo   Permanent Blacklist: Excluded Automatically
echo ========================================================
echo.

if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Starting KBO Belgium Construction Scraper across all Belgian postcodes...
%PYTHON_EXE% -u src\scraper_be_cnst_kbo.py %*
if errorlevel 1 goto RunFailed

echo.
echo ========================================================
echo [SUCCESS] Scraping completed successfully!
echo Output saved to:
echo  - BE_CNST_KBO0_0RAW.csv
echo  - csdl_mlt\BE_CNST_KBO0_0RAW.csv
echo  - archive\be_belgium\BE_CNST_KBO0_0RAW.csv
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

