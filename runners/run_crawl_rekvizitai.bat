@echo off
chcp 65001 >nul
cd /d "%~dp0\.."
title Cào Danh Sách Doanh Nghiệp Rekvizitai (Lithuania)
echo ======================================================================
echo    KHOI DONG BO CAO REKVIZITAI.VZ.LT (SIUVIMAS, MEDZIAGOS)
echo ======================================================================

call .venv\Scripts\activate.bat
python crawlmail\crawl_rekvizitai_siuvimas.py

pause
