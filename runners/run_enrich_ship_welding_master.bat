@echo off
chcp 65001 >nul
title Dual Pipeline Enrich Shipbuilding Subcontractors and Manufacturers

echo ======================================================================
echo  DUAL PIPELINE ENRICH SHIPBUILDING AND SHIP WELDING ENTERPRISES
echo  Sources: KOMEA + BMEA + Deep Web Crawler
echo  Target: KR_SHIP_HIPC_2COL.csv
echo ======================================================================

cd /d "%~dp0\.."

python -u crawlmail\enrich_ship_welding_master.py

echo.
echo Process finished. Please check KR_SHIP_HIPC_2COL.csv in root workspace.
pause
