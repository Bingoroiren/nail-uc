@echo off
title Enrich SIRI Certified Companies Denmark (danmachFT) - Visual Mode
cd /d "%~dp0.."
echo ===============================================================
echo     LAM GIAU DU LIEU SIRI CERTIFIED DENMARK (danmachFT)
echo     [Che do: Hien thi trinh duyet truc quan (headless=False)]
echo     [Quy tac loc: Google Maps + DuckDuckGo/Bing + Deep Crawl]
echo ===============================================================
echo.
python -u crawlmail\enrich_siri_denmark_deep.py %*
echo.
pause
