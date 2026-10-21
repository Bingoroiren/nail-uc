@echo off
chcp 65001 >nul
title Cao Chi Tiet Tung Trang Cong Ty D and B Slovakia (1002 Cong Ty)

echo ======================================================================
echo  CAO CHI TIET TUNG TRANG CONG TY D and B SLOVAKIA (1,002 CONG TY)
echo  Trang: Dia chi so nha, Website, Nguoi dai dien, Quy mo nhan su
echo ======================================================================
echo.

cd /d "%~dp0\.."

echo [*] Khoi chay trinh cao chi tiet profile D and B Slovakia...
.venv\Scripts\python.exe csdl_sk_agcy\enrich_dnb_details.py
if %ERRORLEVEL% NEQ 0 (
    echo [-] Loi xay ra khi chay enrich_dnb_details.py
)

echo.
echo ======================================================================
echo  HOAN TAT! KIEM TRA THU MUC: csdl_sk_agcy
echo ======================================================================
pause
