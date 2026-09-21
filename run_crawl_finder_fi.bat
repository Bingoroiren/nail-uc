@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Crawl Finder.fi - Nhan Su & Tuyen Dung Phan Lan
echo ======================================================================
echo    KHOI DONG BO CAO FINDER.FI (PHAN LAN - FINLAND)
echo    Tu khoa: "Henkilostoovuokraus" (78200) va "Rekrytointi" (78100)
echo    Lay Website, Email, SDT, Doanh thu, Nhan su va Loc trung
echo ======================================================================

call .venv\Scripts\activate.bat
python crawlmail\crawl_finder_fi.py

pause
