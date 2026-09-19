@echo off
title Scrape BC Licensed Foreign Worker Recruiters (Canada)
cd /d "%~dp0.."

echo ===============================================================
echo     CAO DU LIEU NHA TUYEN DUNG LAO DONG NUOC NGOAI (BC, CANADA)
echo     [Che do: Doc luong tren RAM - 0 file PDF luu xuong o dia]
echo     [Trinh duyet truc quan (headless=False)]
echo ===============================================================
echo.

if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

python -u crawlmail\scrape_bc_licensed_recruiters.py %*
echo.
pause
