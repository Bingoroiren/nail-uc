@echo off
chcp 65001 >nul
title Bo Cao Tong Hop CSDL Moi Gioi Lao Dong Slovakia

echo ======================================================================
echo  BO CAO TONG HOP CSDL MOI GIOI LAO DONG SLOVAKIA (3 NGUON)
echo  1. personalneagentury.sk
echo  2. greenpages.sk
echo  3. dnb.com (Dun and Bradstreet - 1,327 cong ty)
echo ======================================================================
echo.

cd /d "%~dp0\.."

echo [1/4] Dang cao personalneagentury.sk...
.venv\Scripts\python.exe csdl_sk_agcy\harvest_personalneagentury.py

echo.
echo [2/4] Dang cao greenpages.sk...
.venv\Scripts\python.exe csdl_sk_agcy\harvest_greenpages_agcy.py

echo.
echo [3/4] Dang cao dnb.com (Dun and Bradstreet Slovakia)...
.venv\Scripts\python.exe csdl_sk_agcy\scrape_dnb_slovakia.py

echo.
echo [4/4] Dang tong hop toan bo CSDL...
.venv\Scripts\python.exe csdl_sk_agcy\consolidate_sk_agcy.py

echo.
echo ======================================================================
echo  HOAN TAT TOAN BO! KIEM TRA THU MUC: csdl_sk_agcy
echo ======================================================================
pause
