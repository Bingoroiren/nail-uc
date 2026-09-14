@echo off
title Crawl & Filter Emails - Farm Finland 11_9
cd /d "%~dp0.."
echo ===============================================================
echo     CRAWL, FILTER JUNK & GUESS EMAILS FOR (11_9) PHAN LAN
echo ===============================================================
echo.
python -u crawlmail\crawl_farm_finland_11_9.py %*
echo.
pause
