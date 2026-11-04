@echo off
chcp 65001 >nul
title Federgon Belgium Members Scraper

echo ========================================================
echo   FEDERGON BELGIUM MEMBERS DIRECTORY SCRAPER
echo   Filters: Projectsourcing and Recruitment, Search and Selection
echo   Permanent Blacklist: Excluded Automatically
echo ========================================================
echo.

cd /d "%~dp0\.."

if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Extracting filtered Federgon members...
%PYTHON_EXE% crawl_federgon.py

echo.
echo Process finished. Check output file: BE_AGCY_WEBD_0RAW.csv
pause
