@echo off
chcp 65001 > nul
echo ======================================================
echo    SCRAPER E-7-3 SHIPBUILDING WELDERS FROM 3 PORTALS
echo    (Work24 + Saramin + JobKorea)
echo ======================================================

set PYTHON_EXE=C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe

if not exist "%PYTHON_EXE%" (
    set PYTHON_EXE=python
)

"%PYTHON_EXE%" crawlmail\scraper_weld_e703.py

echo.
echo [DONE] Scraper finished. Check output in KR_WELD_E703_0RAW.csv
pause
