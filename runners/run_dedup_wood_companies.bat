@echo off
chcp 65001 >nul
title Deduplicate Company Names - Lithuania Wood Datasets
cd /d "%~dp0\.."

echo ========================================================
echo   DEDUPLICATE COMPANY NAMES - LITHUANIA WOOD DATASETS
echo   - Merges headquarters and branches (filialas, skyrius)
echo   - Preserves highest scoring B2B emails, phones, directors
echo   - Pushes 100 percent of companies with email to top rows
echo ========================================================
echo.

if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Running smart deduplication...
%PYTHON_EXE% -u crawlmail\dedup_wood_companies.py %*
if errorlevel 1 goto RunFailed

echo.
echo ========================================================
echo [SUCCESS] Deduplication completed!
echo ========================================================
echo.
pause
goto End

:RunFailed
echo.
echo [ERROR] Deduplication encountered an error!
pause
exit /b 1

:End

