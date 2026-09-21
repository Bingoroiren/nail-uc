@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

cd /d "%~dp0"
title CÀO EMAIL CHO AGENCY CÓ SẴN WEBSITE - PHẦN LAN

echo ===========================================================================
echo   ƯU TIÊN CÀO EMAIL CHO CÁC DOANH NGHIỆP ĐÃ CÓ SẴN WEBSITE (PHẦN LAN)
echo   (Tốc độ siêu nhanh: Quét Website + Fanpage Facebook + Chống chặn bot)
echo   Cửa sổ Chrome hiển thị trực quan (Headless = False)
echo ===========================================================================

if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "%~dp0crawlmail\enrich_maps_agency_fi.py" --web-only
) else (
    python "%~dp0crawlmail\enrich_maps_agency_fi.py" --web-only
)

echo.
echo ===========================================================================
echo   TIẾN TRÌNH HOÀN TẤT HOẶC ĐÃ LƯU AN TOÀN!
echo ===========================================================================
pause
