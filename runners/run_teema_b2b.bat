@echo off
chcp 65001 >nul
title TEEMA Taiwan Electronics Factories High-Speed Scraper Launcher
cd /d "%~dp0.."

echo ======================================================================
echo    HE THONG CAO DU LIEU NHA MAY TEEMA B2B (PHIEN BAN TANG TOC X15)
echo    Nguon: https://b2b.teema.org.tw/
echo    Che do: 10 Luong bat dong bo song song cuc nhanh
echo ======================================================================
echo.

:: Kiem tra moi truong ao .venv
if not exist .venv (
    echo [*] Dang tao moi truong ao .venv...
    python -m venv .venv
)

echo [*] Kich hoat moi truong ao...
call .venv\Scripts\activate.bat

echo [*] Kiem tra cai dat thu vien can thiet...
pip install -r requirements.txt aiohttp beautifulsoup4 >nul 2>&1

echo.
echo ======================================================================
echo    BAT DAU CAO SIEU TOC (TIEN DO SE IN TRUC TIEP TREN MAN HINH)
echo ======================================================================
echo.
python -u src/scraper_teema_b2b.py

echo.
echo ======================================================================
echo    DA KET THUC PHIEN CAO VA SAP XEP DU LIEU TEEMA TAIWAN
echo ======================================================================
pause
