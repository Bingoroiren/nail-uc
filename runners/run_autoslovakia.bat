@echo off
title Slovakia Auto and Metal Industry Scraper
cd /d "%~dp0.."

echo ======================================================
echo    SLOVAKIA AUTOMOTIVE AND METAL INDUSTRY SCRAPER
echo    Target: zlatestranky.sk
echo    Output: AutoSlovakia.csv
echo ======================================================

if exist .venv goto ActivateVenv
echo [*] Error: Virtual environment .venv not found!
pause
exit /b

:ActivateVenv
echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [*] Launching scraper...
python -u src\scraper_autoslovakia.py

if errorlevel 1 goto RunFailed

echo.
echo ======================================================
echo    SCRAPING COMPLETED SUCCESSFULLY!
echo    Output file: AutoSlovakia.csv
echo ======================================================
pause
goto End

:RunFailed
echo.
echo [ERROR] Scraper failed during execution.
pause
exit /b

:End
