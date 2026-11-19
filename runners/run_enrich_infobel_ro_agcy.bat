@echo off
chcp 65001 >nul
title Enrich Romanian Agencies via Infobel Romania
cd /d "%~dp0\.."

echo =======================================================================
echo   DATA ENRICHMENT FOR RO_AGCY_GMAP_2COL.CSV VIA INFOBEL ROMANIA
echo   Source : https://local.infobel.ro/
echo   Mode   : Visible Browser (headless=False) + Manual Captcha Alert (\a)
echo   Target : Search Company, Extract Website, Crawl B2B Recruitment Emails
echo =======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    echo Please install Python virtual environment first.
    pause
    exit /b 1
)

echo [INFO] Starting enrich_infobel_ro_agcy.py...
echo [TIP] If Infobel shows Captcha / Bot Challenge, a chime bell will sound.
echo       Please solve the challenge in the open browser window to resume.
echo.

.venv\Scripts\python.exe -u crawlmail\enrich_infobel_ro_agcy.py %*

if errorlevel 1 (
    echo.
    echo [ERROR] Enrichment script encountered an error!
    pause
    exit /b 1
)

echo.
echo =======================================================================
echo   ENRICHMENT COMPLETED SUCCESSFULLY!
echo   Outputs:
echo     - RO_AGCY_GMAP_2COL.csv (Master 20-col dataset, emails sorted to top)
echo     - RO_AGCY_GMAP_ONLY_EMAILS_READY.csv (Outreach-ready rows)
echo =======================================================================
pause
