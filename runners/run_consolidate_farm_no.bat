@echo off
chcp 65001 >nul
title Consolidate and Deduplicate Norway Agriculture Data

echo ===============================================================================
echo        CONSOLIDATE AND DEDUPLICATE NORWAY AGRICULTURE DATA
echo                 (Proff.no + Gulesider.no)
echo ===============================================================================
echo.

cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at .venv\Scripts\python.exe!
    pause
    exit /b 1
)

echo [INFO] Running consolidate_farm_no.py...
echo.
.venv\Scripts\python.exe crawlmail\consolidate_farm_no.py
if errorlevel 1 (
    echo.
    echo [ERROR] Consolidation script encountered an error!
    pause
    exit /b 1
)

echo.
echo ===============================================================================
echo [SUCCESS] Norway agriculture data successfully merged and deduplicated!
echo ===============================================================================
echo.
pause

