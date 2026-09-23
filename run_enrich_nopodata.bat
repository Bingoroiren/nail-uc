@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Lam Giau Du Lieu Cong Ty Na Uy (NOPROFF -^> NOPODATA.csv)

echo ===========================================================================
echo   TIEN TRINH LAM GIAU DU LIEU: NOPROFF.CSV -^> NOPODATA.CSV
echo   - Nguon 1: Open API Cuc Dang ky Doanh nghiep Na Uy (data.brreg.no)
echo   - Nguon 2: Cao truc tiep Email B2B tu Website doanh nghiep
echo   - Loc sach: Loai bo %%20, loc bo email he thong va email mau
echo   - Luu dong: Ghi de tuc thi vao NOPODATA.csv va Cache JSON
echo   - Ho tro: Tu dong resume khi chay tiep
echo ===========================================================================
echo.

if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

python "crawlmail\enrich_nopodata.py"

echo.
echo ===========================================================================
echo   TIEN TRINH LAM GIAU NOPODATA DA HOAN TAT!
echo ===========================================================================
pause
