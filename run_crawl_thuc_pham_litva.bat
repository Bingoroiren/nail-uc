@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Crawl Thuc Pham Litva (TRACES NT)
echo ======================================================================
echo    KHOI DONG BO CAO CHE BIEN THUC PHAM LITVA (TRACES NT - EU)
echo    Nguon: https://webgate.ec.europa.eu/tracesnt/
echo ======================================================================

call .venv\Scripts\activate.bat
python crawlmail\crawl_traces_thuc_pham_litva.py

pause
