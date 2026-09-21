@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Lam giau thuc pham Litva qua Rekvizitai.vz.lt
echo ======================================================================
echo    KHOI DONG LAM GIAU DOANH NGHIEP THUC PHAM LITVA QUA REKVIZITAI.VZ.LT
echo    Che do: Trinh duyet Chrome truc quan (headless=False)
echo ======================================================================
echo.
echo [*] Luu y: Neu trinh duyet Chrome xuat hien o xac minh Cloudflare
echo     ("Verify you are human"), ban chi can bam 1 lan vao o vuong.
echo.

call .venv\Scripts\activate.bat
python crawlmail\enrich_thuc_pham_litva_rekvizitai.py

pause
