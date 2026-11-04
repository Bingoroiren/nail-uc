@echo off
chcp 65001 >nul
title KBO Belgium Wood Processing Scraper
cd /d "%~dp0\.."

echo ========================================================
echo   KBO BELGIUM WOOD AND CARPENTRY SCRAPER
echo   Codes (NACE): 16110, 16120, 16210, 16220, 16230,
echo                 16250, 16270, 16281
echo   Mode: Visual Browser (headless=False) with AI OCR Captcha
echo   Source: KBO Public Search (Official Belgian Registry)
echo   Output: BE_WOOD_KBO0_0RAW.csv (Rule 10: 17 characters)
echo   Postcodes: 1187 Belgian Postcodes
echo   Permanent Blacklist: Excluded Automatically
echo ========================================================
echo.

if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Starting KBO Belgium Wood Scraper across all Belgian postcodes...
%PYTHON_EXE% -u src\scraper_be_wood_kbo.py %*
if errorlevel 1 goto RunFailed

echo.
echo ========================================================
echo [SUCCESS] Scraping completed successfully!
echo Output saved to:
echo  - BE_WOOD_KBO0_0RAW.csv
echo  - csdl_mlt\BE_WOOD_KBO0_0RAW.csv
echo  - archive\be_belgium\BE_WOOD_KBO0_0RAW.csv
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

