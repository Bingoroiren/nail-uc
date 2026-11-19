@echo off
chcp 65001 >nul
title Thu Thap va Hop Nhat Nhan Su va Zeitarbeit Duc (DE_AGCY_WEBD)

echo ======================================================================
echo   HE THONG THU THAP VA HOP NHAT NHAN SU VA ZEITARBEIT DUC (DE_AGCY_WEBD)
echo   Nguon: wer-zu-wem.de (43 pages, 327 groups) + gelbeseiten.de (Personalvermittlung + Zeitarbeit)
echo   Tuan thu: GEMINI.md (Rule 1, 2, 3, 5, 8, 9, 10, 11, 12)
echo ======================================================================
echo.

cd /d "%~dp0\.."

set "PYTHON_EXE=.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=python"
)

echo [*] Dang khoi chay tien trinh thu thap va hop nhat toan bo cac vung...
echo.

"%PYTHON_EXE%" crawlmail\scrape_de_agcy_merged.py %*

echo.
echo ======================================================================
echo   TIEN TRINH DA HOAN TAT!
echo   Vui long kiem tra cac file dau ra:
echo   1. DE_AGCY_WEBD_0RAW.csv
echo   2. DE_AGCY_WEBD_2COL.csv
echo   3. DE_AGCY_WEBD_ONLY_EMAILS_READY.csv
echo ======================================================================
pause
