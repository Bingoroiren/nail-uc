@echo off
chcp 65001 >nul
title Scrape Rekvizitai Wood and Furniture - Lithuania
cd /d "%~dp0\.."

echo ========================================================
echo   SCRAPER REKVIZITAI.VZ.LT - WOOD AND FURNITURE
echo   Visual Browser Mode (Headless = False)
echo   Supports manual Captcha and Turnstile solving on screen
echo ========================================================
echo.

if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Starting visual browser for Rekvizitai...
%PYTHON_EXE% -u crawlmail\harvest_rekvizitai_wood.py %*
if errorlevel 1 goto RunFailed

echo.
echo ========================================================
echo [SUCCESS] Rekvizitai wood scraper and merger completed!
echo ========================================================
echo.
pause
goto End

:RunFailed
echo.
echo [ERROR] Process encountered an error!
pause
exit /b 1

:End

