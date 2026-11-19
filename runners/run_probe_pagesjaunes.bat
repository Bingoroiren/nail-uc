@echo off
chcp 65001 >nul
title Probe and Solve PagesJaunes Security

cd /d "%~dp0\.."

echo ======================================================================
echo    PAGESJAUNES FRANCE SECURITY SOLVER AND DOM INSPECTOR
echo ======================================================================
echo.

.venv\Scripts\python.exe scratch\probe_pagesjaunes.py

echo.
echo ======================================================================
echo    COMPLETED
echo ======================================================================
pause

