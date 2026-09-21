@echo off
chcp 65001 >nul
title Quet Email Doanh Nghiep Che Bien Thuc Pham Litva

echo ===========================================================================
echo   BAT DAU QUET EMAIL CHO DOANH NGHIEP CHE BIEN THUC PHAM LITVA TU WEBSITE
echo ===========================================================================

cd /d "%~dp0"

if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "crawlmail\crawl_emails_thuc_pham_litva.py"
) else if exist ".\.venv\Scripts\python.exe" (
    ".\.venv\Scripts\python.exe" "crawlmail\crawl_emails_thuc_pham_litva.py"
) else (
    python "crawlmail\crawl_emails_thuc_pham_litva.py"
)

echo.
echo ===========================================================================
echo   DA HOAN TAT QUET EMAIL!
echo ===========================================================================
pause
