@echo off
chcp 65001 >nul
title Parse PagesJaunes Saved HTML Files (FR_AGCY_PJAU)

cd /d "%~dp0\.."

echo ======================================================================
echo    PARSER PAGESJAUNES HTML FILES
echo    Input:  scratch\pj_*.html
echo    Output: FR_AGCY_PJAU_0RAW.csv
echo ======================================================================
echo.

.venv\Scripts\python.exe crawlmail\parse_pagesjaunes_html.py

echo.
echo ======================================================================
echo    COMPLETED
echo ======================================================================
pause

