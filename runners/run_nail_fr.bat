@echo off
chcp 65001 >nul
title Cao Du Lieu Tiem Nail Phap Tren Google Maps (FR_NAIL_GMAP)

echo ======================================================================
echo   HE THONG CAO DU LIEU TIEM NAIL VA LAM DEP TAI PHAP (FR_NAIL_GMAP)
echo   TU KHOA: Institut de beaute, Salon de manucure, Bar a ongles
echo   Tuan thu: GEMINI.md (Rule 1, 2, 3, 4, 5, 8, 9, 10, 11, 12)
echo ======================================================================
echo.

cd /d "%~dp0\.."

set "PYTHON_EXE=.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=python"
)

echo [*] Python executable: %PYTHON_EXE%
echo [*] Buoc 1: Cao Google Maps truc quan voi Playwright Chromium (headless=False)
echo [*] Buoc 2: Boc tach Email da tang (Cloudflare, WP Encoder, ROT13) va format 20 cot ColdMail
echo ----------------------------------------------------------------------
echo.

echo [+] DANG KHOI DONG ENGINE CAO GOOGLE MAPS PHAP...
"%PYTHON_EXE%" src\scraper_nail_fr.py %*

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [-] Engine cao Google Maps ket thuc hoac bi gian doan.
)

echo.
echo [+] DANG KHOI DONG TIEN TRINH BOC TACH EMAIL VA XUAT FILE COLD MAIL...
"%PYTHON_EXE%" crawlmail\preprocess_csv_nail_fr.py

echo.
echo ======================================================================
echo   HOAN TAT TRON GOI CHIEN DICH TIEM NAIL PHAP!
echo   Cac tep dau ra chuan Rule 10:
echo   1. FR_NAIL_GMAP_0RAW.csv (Du lieu tho tu Google Maps)
echo   2. FR_NAIL_GMAP_1ENR.csv (CSDL da lam giau day du)
echo   3. FR_NAIL_GMAP_2COL.csv (Cold Mail 20 cot, 100%% email len dau)
echo   4. FR_NAIL_GMAP_ONLY_EMAILS_READY.csv (Chi chua tiem co email)
echo ======================================================================
pause
