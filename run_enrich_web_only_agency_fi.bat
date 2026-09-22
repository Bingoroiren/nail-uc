@echo off
chcp 65001 >nul
title Cao Email Cho Agency Co San Website - Phan Lan

echo ===========================================================================
echo   UU TIEN CAO EMAIL CHO DOANH NGHIEP CO SAN WEBSITE - PHAN LAN
echo ===========================================================================

cd /d "%~dp0"

"%~dp0.venv\Scripts\python.exe" "%~dp0crawlmail\enrich_maps_agency_fi.py" --web-only

echo.
echo ===========================================================================
echo   DA HOAN TAT TIEN TRINH!
echo ===========================================================================
pause
