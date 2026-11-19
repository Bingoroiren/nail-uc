@echo off
chcp 65001 >nul
title Filter Mail Tracker and CleanData for LT_WOOD_INLT

cd /d "%~dp0\.."

echo ======================================================================
echo    FILTER TRACKER AND CLEANDATA FOR LT_WOOD_INLT
echo    Input:  LT_WOOD_INLT_2COL.csv
echo    Ref 1:  Mail Tracker - mail.csv
echo    Ref 2:  LT_WOOD_COMB - CleanData.csv
echo    Output: LT_WOOD_INLT_2COL.csv (Cleaned)
echo            LT_WOOD_INLT_ONLY_EMAILS_READY.csv
echo            archive\lt_lithuania\LT_WOOD_INLT_DA_LOAI_BO_REPLY_BOUNCE.csv
echo ======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    pause
    exit /b 1
)

.venv\Scripts\python.exe crawlmail\filter_tracker_lt_wood_inlt.py

echo.
echo ======================================================================
echo    COMPLETED
echo ======================================================================
pause

