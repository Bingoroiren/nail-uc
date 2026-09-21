@echo off
chcp 65001 >nul
title Lam Giau Du Lieu Agency Phan Lan (Google Maps + Search + Facebook)

echo ===========================================================================
echo   LAM GIAU DU LIEU AGENCY PHAN LAN (HENKILOSTOVUOKRAUS & REKRYTOINTI)
echo   (Google Maps hl=fi + Fallback Search + Facebook + Xu ly %20 + Anti-Bot)
echo   Trinh duyet se hien thi (Headless = False) de ban tien theo doi!
echo ===========================================================================

cd /d "%~dp0"

if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "crawlmail\enrich_maps_agency_fi.py"
) else if exist ".\.venv\Scripts\python.exe" (
    ".\.venv\Scripts\python.exe" "crawlmail\enrich_maps_agency_fi.py"
) else (
    python "crawlmail\enrich_maps_agency_fi.py"
)

echo.
echo ===========================================================================
echo   DA HOAN TAT LICH TRINH!
echo ===========================================================================
pause
