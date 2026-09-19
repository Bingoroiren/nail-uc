@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo ========================================================
echo   CÀO DỮ LIỆU GIẤY PHÉP MÔI GIỚI MANITOBA (WRAPA)
echo   Nạp vào file: môi giới Canada  - CleanData.csv
echo ========================================================
echo.
python crawlmail\scrape_mb_licensed_recruiters.py
echo.
pause
