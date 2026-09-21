@echo off
chcp 65001 >nul
title Lam Giau Du Lieu Che Bien Thuc Pham Litva (Google Maps + Search + Facebook)

echo ===========================================================================
echo   LAM GIAU DU LIEU CHE BIEN THUC PHAM LITVA
echo   (Google Maps hl=lt + Fallback Search + Facebook + Anti-Bot Alert)
echo   Trinh duyet se hien thi (Headless = False) de ban tien theo doi!
echo ===========================================================================

cd /d "%~dp0"

if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "crawlmail\enrich_maps_thuc_pham_litva.py"
) else if exist ".\.venv\Scripts\python.exe" (
    ".\.venv\Scripts\python.exe" "crawlmail\enrich_maps_thuc_pham_litva.py"
) else (
    python "crawlmail\enrich_maps_thuc_pham_litva.py"
)

echo.
echo ===========================================================================
echo   DA HOAN TAT LICH TRINH!
echo ===========================================================================
pause
