@echo off
chcp 65001 >nul
title Rekvizitai Lithuania Labour Exchange Scraper and Enrichment
color 0A
cd /d "%~dp0.."

echo ===============================================================================
echo     HE THONG CAO VA LAM GIAU DU LIEU REKVIZITAI LITHUANIA (RECRUITMENT)
echo   - Nguon: https://rekvizitai.vz.lt/en/companies/labour_exchange_employment/
echo   - Boc tach: Thu ba + Website chinh thuc + Facebook Fanpage + Email lien he
echo ===============================================================================
echo.

python src\scraper_rekvizitai_lithuania.py

echo.
echo ===============================================================================
echo   Tien trinh cao va lam giau du lieu Rekvizitai da hoan tat!
echo ===============================================================================
pause
