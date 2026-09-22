@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Lam Giau Du Lieu ADENVIRK (Google Maps hl=da + Chrome)

echo ===========================================================================
echo   LAM GIAU DU LIEU CHO ADENVIRK.CSV -^> ADENVMAP.CSV (GOOGLE MAPS DAN MACH)
echo   - Muc tieu: Cac ban ghi CHUA CO EMAIL tu ADENVIRK.csv
echo   - Quy tac so khop ten nghiem ngat (Exact, Ngoac don, Gach ngang)
echo   - Trinh duyet: Google Chrome (ggchrome, hl=da)
echo   - Cao Email va SDT truc tiep tu Website (loai bo %%20, loc mail rac)
echo   - Chon duy nhat 1 Email co gia tri B2B cao nhat cho Moi gioi Lao dong
echo   - Luu file dong truc tiep vao ADENVMAP.csv va Cache JSON
echo ===========================================================================
echo.

if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

python "crawlmail\enrich_maps_aden_virk.py"

echo.
echo ===========================================================================
echo   TIEN TRINH DA HOAN TAT HOAC DA LUU TRANG THAI TIEN DO THANH CONG!
echo ===========================================================================
pause
