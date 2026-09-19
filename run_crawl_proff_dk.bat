@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Cào Danh Sách Doanh Nghiệp Proff.dk (Arbejdskrafts tjenester)
echo ======================================================================
echo    KHOI DONG BO CAO PROFF.DK (CVR, SĐT, EMAIL, ĐỊA CHỈ DOANH NGHIỆP)
echo    Nguồn: https://www.proff.dk/branchesøg?q=Arbejdskrafts tjenester
echo ======================================================================

call .venv\Scripts\activate.bat
python crawlmail\crawl_proff_dk.py

pause
