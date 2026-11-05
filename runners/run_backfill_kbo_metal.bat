@echo off
chcp 65001 >nul
title Backfill KBO Official Details - Belgium Metal (Playwright and AI OCR)
cd /d "%~dp0\.."

echo ========================================================
echo   BACKFILL KBO OFFICIAL CONTACT DETAILS - BELGIUM METAL
echo   Input: BE_METL_KBO0_0RAW.csv (14,316 deduplicated companies)
echo   Engine: Visual Browser (headless=False) + AI OCR Captcha
echo   Anti-Block: 100 percent bypass via ddddocr solver
echo   Cache: crawlmail\cache_kbo_backfill_be_metl_kbo0_0raw.json
echo   Resume: 100 percent checkpoint support
echo   Pulls: Official FOD Economie Email, Website, Phone
echo ========================================================
echo.

if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Starting KBO detail backfill for Belgium Metal enterprises...
%PYTHON_EXE% -u crawlmail\backfill_kbo_details.py BE_METL_KBO0_0RAW.csv %*
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
