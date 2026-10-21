@echo off
chcp 65001 >nul
title Build CSDL Slovakia and Enrich Datasets

echo ======================================================================
echo   BUILD CSDL SLOVAKIA KNOWLEDGE BASE AND ENRICH DATASETS
echo   Target Folder : csdl_sk/
echo   Sources       : Azet (All Pages), Greenpages (All Pages), ZAP SR
echo   Purpose       : Harvest permanent Slovak business directories and enrich
echo ======================================================================
echo.

cd /d "%~dp0\.."

set PYTHON_BIN=.venv\Scripts\python.exe
if not exist "%PYTHON_BIN%" (
    set PYTHON_BIN=python
)

echo [1/3] Harvesting all pages from Greenpages Automotive...
"%PYTHON_BIN%" csdl_sk\harvest_greenpages_full.py

echo.
echo [2/3] Harvesting all pages from Azet Automotive (2500+ companies)...
"%PYTHON_BIN%" csdl_sk\harvest_azet_full.py

echo.
echo [3/3] Cross-matching and enriching SK_AUTO_SLVD_1ENR.csv...
"%PYTHON_BIN%" csdl_sk\enrich_from_csdl.py

echo.
echo ======================================================================
echo   CSDL BUILD AND ENRICHMENT COMPLETED!
echo ======================================================================
pause
