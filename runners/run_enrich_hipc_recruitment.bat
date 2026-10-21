@echo off
chcp 65001 >nul
title Pipeline Enrich Shipbuilding Subcontractors and Welder Recruitment Emails

echo ======================================================================
echo  PIPELINE ENRICH SHIPBUILDING SUBCONTRACTORS AND WELDER RECRUITMENT
echo  Target: KR_SHIP_HIPC_2COL.csv (Saramin and Web Footprint B2B Emails)
echo ======================================================================

cd /d "%~dp0\.."

python crawlmail\enrich_hipc_recruitment.py

echo.
echo Process finished. Please check KR_SHIP_HIPC_2COL.csv in root workspace.
pause
