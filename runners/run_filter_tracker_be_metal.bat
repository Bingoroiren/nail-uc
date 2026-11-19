@echo off
chcp 65001 >nul
title Filter Mail Tracker and CleanData for BE_METL_KBO0

cd /d "%~dp0\.."

echo ======================================================================
echo    FILTER TRACKER AND CLEANDATA FOR BE_METL_KBO0
echo    Input:  BE_METL_KBO0_2COL.csv
echo    Ref 1:  Mail Tracker - mail.csv
echo    Ref 2:  BE_METAL_KBO - CleanData.csv
echo    Output: BE_METL_KBO0_2COL.csv (Cleaned)
echo            BE_METL_KBO0_ONLY_EMAILS_READY.csv
echo            archive\be_belgium\BE_METL_KBO0_DA_LOAI_BO_REPLY_BOUNCE.csv
echo ======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    pause
    exit /b 1
)

.venv\Scripts\python.exe crawlmail\filter_tracker_be_metal.py

echo.
echo ======================================================================
echo    COMPLETED
echo ======================================================================
pause

