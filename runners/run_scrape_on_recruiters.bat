@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo ========================================================
echo   CÀO DỮ LIỆU CẤP PHÉP MÔI GIỚI & THA ONTARIO
echo   Nạp vào file: môi giới Canada  - CleanData.csv
echo ========================================================
echo.
python crawlmail\scrape_on_licensed_recruiters.py
echo.
pause
