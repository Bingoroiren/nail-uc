@echo off
chcp 65001 >nul
title KBO Belgium Meat Processing Scraper
cd /d "%~dp0\.."

echo ========================================================
echo   KBO BELGIUM MEAT PROCESSING AND SLAUGHTERHOUSE SCRAPER
echo   Codes (5-digit): 10111, 10112, 10113, 10119, 10120, 10130
echo   Covers: 100% meat subcodes (1012001..3, 1013001..11)
echo   Mode: Visual Browser (headless=False) for direct monitoring
echo   Source: KBO Public Search (Official Belgian Registry)
echo   Output: BE_MEAT_KBO0_0RAW.csv (Rule 10: 17 characters)
echo   Postcodes: 1187 Belgian Postcodes
echo   Permanent Blacklist: Excluded Automatically
echo ========================================================
echo.

if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Starting KBO Belgium Meat Scraper across all Belgian postcodes...
%PYTHON_EXE% -u src\scraper_be_meat_kbo.py %*
if errorlevel 1 goto RunFailed

echo.
echo ========================================================
echo [SUCCESS] Scraping completed successfully!
echo Output saved to:
echo  - BE_MEAT_KBO0_0RAW.csv
echo  - csdl_mlt\BE_MEAT_KBO0_0RAW.csv
echo  - archive\be_belgium\BE_MEAT_KBO0_0RAW.csv
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

