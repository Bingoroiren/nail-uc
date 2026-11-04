@echo off
chcp 65001 >nul
title Backfill KBO Official Contact Details - Belgium Meat
cd /d "%~dp0\.."

echo ========================================================
echo   BACKFILL KBO OFFICIAL CONTACT DETAILS - BELGIUM MEAT
echo   Input: BE_MEAT_KBO0_0RAW.csv
echo   Speed: Multi-threaded Direct HTTP GET (0 percent Captcha)
echo   Pulls: Official FOD Economie Email, Website, Phone
echo ========================================================
echo.

if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Starting fast KBO detail backfill for Belgium Meat enterprises...
%PYTHON_EXE% -u crawlmail\backfill_kbo_details.py BE_MEAT_KBO0_0RAW.csv --workers 16 %*
if errorlevel 1 goto RunFailed

echo.
echo ========================================================
echo [SUCCESS] KBO detail backfill completed!
echo ========================================================
echo.
pause
goto End

:RunFailed
echo.
echo [ERROR] Backfill process encountered an error!
pause
exit /b 1

:End

