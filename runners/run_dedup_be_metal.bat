@echo off
chcp 65001 >nul
title Deduplicate Belgium Metal Enterprises - KBO Registry
cd /d "%~dp0\.."

echo ========================================================
echo   DEDUPLICATE BELGIUM METAL ENTERPRISES (KBO REGISTRY)
echo   Input: BE_METL_KBO0_0RAW.csv
echo   Logic: Merge branches (VE) and entities (ENT RP, ENT NP)
echo   Output: Clean deduplicated BE_METL_KBO0_0RAW.csv
echo   Backup: archive\be_belgium\BE_METL_KBO0_0RAW_before_dedup.csv
echo   Rules: CSV UTF-8 with BOM, Phone with '+32, Blacklist check
echo ========================================================
echo.

if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Starting deduplication process...
%PYTHON_EXE% -u crawlmail\dedup_be_metal.py %*
if errorlevel 1 goto RunFailed

echo.
echo ========================================================
echo [SUCCESS] Deduplication completed successfully!
echo Files synchronized:
echo  - BE_METL_KBO0_0RAW.csv
echo  - csdl_mlt\BE_METL_KBO0_0RAW.csv
echo  - archive\be_belgium\BE_METL_KBO0_0RAW.csv
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

