@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Cào Danh Sách Doanh Nghiệp Proff.dk (Arbejdskrafts tjenester)
echo ======================================================================
echo    KHOI DONG BO CAO PROFF.DK (CVR, SĐT, EMAIL, ĐỊA CHỈ DOANH NGHIỆP)
echo    Nguồn: https://www.proff.dk/branchesøg?q=Arbejdskrafts tjenester
echo    [Chế độ: Đã tối ưu cho mạng VPN - Timeout 60s, Delay 2.5s, Retry 5 lần]
echo ======================================================================

if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe -u crawlmail\crawl_proff_dk.py --timeout 60 --delay 2.5 %*
) else (
    python -u crawlmail\crawl_proff_dk.py --timeout 60 --delay 2.5 %*
)

pause
