@echo off
chcp 65001 >nul
cd /d "%~dp0\.."

echo =====================================================================
echo  LAM GIAU DU LIEU NONG NGHIEP NA UY QUA GULESIDER (JORDBRUK)
echo  NGUON: https://www.gulesider.no/jordbruk/bedrifter
echo =====================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Khong tim thay Python tai .venv\Scripts\python.exe
    pause
    exit /b 1
)

echo Dang khoi chay bo lam giau du lieu nong nghiep Gulesider...
echo.
.venv\Scripts\python.exe crawlmail\enrich_gulesider_farm_no.py --start-page 1 --max-pages 48 --concurrency 4

echo.
echo =====================================================================
echo  HOAN TAT TIEN TRINH LAM GIAU GULESIDER NA UY
echo =====================================================================
pause

