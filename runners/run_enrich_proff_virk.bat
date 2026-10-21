@echo off
chcp 65001 >nul
cd /d "%~dp0.."
title Enrich Proff.dk qua DataCVR.virk.dk (Loc trung va Lay Email Chinh Thuc)
echo ======================================================================
echo    BO LOC TRUNG THEO CVR VA ENRICH EMAIL TU DATACVR.VIRK.DK
echo    Nguon du lieu: proff_arbejdskrafts_tjenester.csv
echo    Che do: Trinh duyet truc quan (headless=False) - Tu dong luu Checkpoint
echo    Co che: Tu dong phat hien va tam dung cho vuot Cloudflare Turnstile
echo    Cau hinh VPN: Timeout 90s, Delay 3.5s, Cloudflare-wait 180s
echo ======================================================================

if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe -u crawlmail\enrich_proff_virk.py --timeout 90 --delay 3.5 %*
) else (
    python -u crawlmail\enrich_proff_virk.py --timeout 90 --delay 3.5 %*
)

pause
