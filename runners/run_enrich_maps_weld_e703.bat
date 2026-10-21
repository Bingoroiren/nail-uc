@echo off
chcp 65001 > nul
echo ======================================================
echo    ENRICH E-7-3 SHIPBUILDING WELDERS VIA GOOGLE MAPS
echo    (KR_WELD_E703_0RAW to KR_WELD_E703_2COL)
echo ======================================================

set PYTHON_EXE=C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe

if not exist "%PYTHON_EXE%" (
    set PYTHON_EXE=python
)

"%PYTHON_EXE%" crawlmail\enrich_maps_weld_e703.py

echo.
echo [DONE] Enrichment finished.
pause
