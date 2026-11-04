@echo off
chcp 65001 >nul
title Filter Tracker and Reconcile Norway Agency CleanData

echo ========================================================
echo   FILTER TRACKER AND RECONCILE NORWAY AGENCY CLEANDATA
echo   Target 1: NO_AGCY_WEBD_2COL.csv
echo   Target 2: (xong 9_29) moi gioi na uy - CleanData.csv
echo   Cross-check: Mail Tracker - mail.csv
echo   Remove: Bounces, Replies, Duplicates
echo ========================================================
echo.

cd /d "%~dp0\.."

if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Starting reconciliation and filtering...
%PYTHON_EXE% crawlmail\filter_and_reconcile_no_agcy.py

echo.
echo Process completed!
pause

