@echo off
chcp 65001 >nul
title Cao Email Cho Agency Co San Website - Phan Lan

echo ===========================================================================
echo   UU TIEN CAO EMAIL CHO DOANH NGHIEP CO SAN WEBSITE (PHAN LAN)
echo   (Toc do cao: Quet Website va Fanpage Facebook)
echo   Trinh duyet hien thi truc quan (Headless = False)
echo ===========================================================================

cd /d "%~dp0"

if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "crawlmail\enrich_maps_agency_fi.py" --web-only
) else if exist ".\.venv\Scripts\python.exe" (
    ".\.venv\Scripts\python.exe" "crawlmail\enrich_maps_agency_fi.py" --web-only
) else (
    python "crawlmail\enrich_maps_agency_fi.py" --web-only
)

echo.
echo ===========================================================================
echo   DA HOAN TAT LICH TRINH!
echo ===========================================================================
pause
