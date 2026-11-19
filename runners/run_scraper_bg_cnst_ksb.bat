@echo off
chcp 65001 >nul
title Scraper - Bulgarian Construction Chamber Register (register.ksb.bg)
cd /d "%~dp0\.."

echo =======================================================================
echo   BULGARIAN CONSTRUCTION CHAMBER SCRAPER (register.ksb.bg)
echo   Target: Central Professional Register of Builders (CPRS / KSB)
echo   Output: BG_CNST_KSBB_0RAW.csv + BG_CNST_KSBB_2COL.csv
echo =======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    echo Please install Python virtual environment first.
    pause
    exit /b 1
)

echo [INFO] Running scraper_bg_cnst_ksb.py...
echo Phase 1: Gathering all builder IDs across all provinces and categories
echo Phase 2: Extracting Section 6 and 5 contacts, manager, phone, email
echo.

.venv\Scripts\python.exe src\scraper_bg_cnst_ksb.py %*

if errorlevel 1 (
    echo.
    echo [ERROR] Scraper encountered an error!
    pause
    exit /b 1
)

echo.
echo =======================================================================
echo   SCRAPING COMPLETED SUCCESSFULLY!
echo   Outputs:
echo     - BG_CNST_KSBB_0RAW.csv (Master raw dataset)
echo     - BG_CNST_KSBB_2COL.csv (Cold Mail 20-column format, emails on top)
echo     - BG_CNST_KSBB_ONLY_EMAILS_READY.csv (Outreach-ready rows)
echo =======================================================================
pause

