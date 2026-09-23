@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Cao Danh Sach 5958 Cong Ty Tu Proff.no (Arbeidskrafttjenester)

echo ===========================================================================
echo   TIEN TRINH CAO DANH SACH CONG TY TU PROFF.NO (NA UY) -^> NOPROFF.CSV
echo   - Nganh nghe: Arbeidskrafttjenester (Nhan luc, Tuyen dung, Viec lam)
echo   - Quy mo: ~5.958 cong ty tren 239 trang ket qua
echo   - Thu thap: Orgnr, Ten cty, SDT, Email, Website, Dia chi, Nhan vien, Doanh thu
echo   - Co che: Luu dong tuc thi sau moi trang vao NOPROFF.csv va Cache JSON
echo   - Ho tro: Tu dong resume neu bi gian doan
echo ===========================================================================
echo.

if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

python "crawlmail\crawl_proff_no.py"

echo.
echo ===========================================================================
echo   TIEN TRINH CAO PROFF.NO DA HOAN TAT!
echo ===========================================================================
pause
