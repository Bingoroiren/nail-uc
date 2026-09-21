@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Enrich Proff.dk via DataCVR.virk.dk (Loc trung & Tim Email Chinh Thuc)
echo ======================================================================
echo    BỘ LỌC TRÙNG THEO CVR VÀ ENRICH EMAIL TỪ DATACVR.VIRK.DK
echo    Nguồn dữ liệu: proff_arbejdskrafts_tjenester.csv
echo    Chế độ: Trình duyệt trực quan (headless=False) - Tự động lưu Checkpoint
echo ======================================================================

if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe -u crawlmail\enrich_proff_virk.py %*
) else (
    python -u crawlmail\enrich_proff_virk.py %*
)

pause
