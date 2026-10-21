@echo off
chcp 65001 >nul
cd /d "%~dp0.."
title RESET CACHE VA CVR ENRICH PROFF.DK QUA VIRK
echo ======================================================================
echo    RESET TOAN BO CACHE VA CAO LAI TU DAU CHO PROFF.DK QUA VIRK
echo    Cau hinh VPN: Timeout 90s, Delay 3.5s, Cloudflare-wait 180s
echo ======================================================================

if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe -u crawlmail\enrich_proff_virk.py --reset --timeout 90 --delay 3.5 %*
) else (
    python -u crawlmail\enrich_proff_virk.py --reset --timeout 90 --delay 3.5 %*
)

pause
