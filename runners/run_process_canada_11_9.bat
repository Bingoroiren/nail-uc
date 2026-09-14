@echo off
title Process Cold Mail File - Canada Certified Companies (11_9)
cd /d "%~dp0.."
echo ===============================================================
echo     PROCESS COLD MAIL FILE - CANADA (11_9)
echo ===============================================================
echo.
python -u crawlmail\process_canada_certified_companies_11_9.py %*
echo.
pause
