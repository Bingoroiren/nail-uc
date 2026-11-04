@echo off
chcp 65001 >nul
title Loc bo trung Mail Tracker va WKOS CleanData cho Agency Ao

echo ======================================================================
echo  LOC BO CONG TY TRUNG MAIL TRACKER VA WKOS CLEANDATA (AUSTRIA AGENCY)
echo ======================================================================

set SCRIPT_DIR=%~dp0..
cd /d "%SCRIPT_DIR%"

python crawlmail\filter_tracker_and_wkos.py

echo.
echo ======================================================================
echo  HOAN TAT!
echo ======================================================================
pause
