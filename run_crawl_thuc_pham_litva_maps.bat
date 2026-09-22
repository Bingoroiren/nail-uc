@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Cao Du Lieu Doanh Nghiep Thuc Pham Litva (Google Maps hl=lt + Chrome)

echo ===========================================================================
echo   BO CAO DOANH NGHIEP CHE BIEN THUC PHAM LITVA (LITHUANIA)
echo   - Nguon: Google Maps (hl=lt)
echo   - Trinh duyet: Google Chrome (ggchrome)
echo   - Muc zoom: 11z
echo   - Loc 22 Tag chuan tieng Litva va Dich nghia Tieng Viet
echo   - Tu dong cao Email va SDT truc tiep tu Website
echo   - Bo qua cac cong ty da co Email trong file Rekvizitai cu
echo   - Luu du lieu dong tuc thi (CSV UTF-8-BOM va Excel) chong mat du lieu
echo ===========================================================================
echo.

if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

python "src\scraper_thuc_pham_lt.py"

echo.
echo ===========================================================================
echo   TIEN TRINH DA HOAN TAT HOAC DA LUU TRANG THAI TIEN DO THANH CONG!
echo ===========================================================================
pause
