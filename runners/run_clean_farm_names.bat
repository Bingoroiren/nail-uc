@echo off
chcp 65001 >nul
cd /d "%~dp0\.."

echo =====================================================================
echo  CHUAN HOA VA LAM SACH TEN DOANH NGHIEP NONG NGHIEP NA UY
echo  Giai ma: %26 -> &, %C3% -> ae, o, a... va bo dia danh thua
echo =====================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Khong tim thay Python tai .venv\Scripts\python.exe
    pause
    exit /b 1
)

.venv\Scripts\python.exe crawlmail\clean_farm_names.py

echo.
echo =====================================================================
echo  HOAN TAT CHUAN HOA DU LIEU NA UY
echo =====================================================================
pause

