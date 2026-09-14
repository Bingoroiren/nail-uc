@echo off
title Enrich SIRI Certified Companies via Virk.dk (Denmark)
cd /d "%~dp0.."
echo ===============================================================
echo     ENRICH SIRI CERTIFIED COMPANIES VIA VIRK.DK (DENMARK)
echo     [Che do: Hien thi trinh duyet truc quan (headless=False)]
echo ===============================================================
echo.
python -u crawlmail\enrich_siri_cvr_denmark.py %*
echo.
pause
