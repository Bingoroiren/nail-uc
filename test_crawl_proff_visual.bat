@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Kiem Tra Muc Do Chan Proff.dk (Visual Mode - Headless OFF)
echo ======================================================================
echo    KIỂM TRA MỨC ĐỘ CHẶN PROFF.DK (MỞ TRÌNH DUYỆT TRỰC QUAN - HEADLESS OFF)
echo    Mục đích: Kiểm tra xem IP VPN có bị Cloudflare / WAF / Captcha chặn không
echo ======================================================================

if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe -u crawlmail\test_proff_visual.py %*
) else (
    python -u crawlmail\test_proff_visual.py %*
)

pause
