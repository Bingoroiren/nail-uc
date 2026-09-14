@echo off
title Enrich Meat Establishments Denmark (Thit dan mach enrich) - Visual Mode
cd /d "%~dp0.."

echo ===============================================================
echo     LAM GIAU DU LIEU THIT DAN MACH -> Thit dan mach enrich
echo     [Che do: Hien thi trinh duyet truc quan (headless=False)]
echo     [Quy tac loc: Google Maps + Bing Search + Deep Crawl]
echo ===============================================================

echo.

if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

python -u crawlmail\enrich_thit_dan_mach_deep.py %*
echo.
pause
