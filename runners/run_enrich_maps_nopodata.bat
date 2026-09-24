@echo off
title Google Maps Company Name Enrichment - NOPODATA.csv
cd /d "%~dp0.."

echo ======================================================================
echo    HE THONG LAM GIAU DU LIEU GOOGLE MAPS THEO TEN CTY (NOPODATA.CSV)
echo ======================================================================
echo.

:: Kiem tra moi truong ao .venv
if not exist .venv (
    echo [*] Khoi tao moi truong ao .venv...
    python -m venv .venv
)

echo [*] Kich hoat moi truong ao...
call .venv\Scripts\activate.bat

echo [*] Cai dat cac thu vien can thiet...
pip install -r requirements.txt >nul 2>&1
playwright install chromium >nul 2>&1

echo.
echo ======================================================================
echo    BAT DAU CHAY ENRICH (TRINH DUYET SE MO DE BAN THEO DOI)
echo ======================================================================
echo.
python crawlmail/enrich_maps_nopodata.py

echo.
echo ======================================================================
echo    DA KET THUC PHIEN LAM GIAU DU LIEU
echo ======================================================================
pause
