@echo off
chcp 65001 >nul
cd /d "%~dp0\.."

echo ==============================================================================
echo [INFO.LT ENRICHMENT] Enriching Lithuanian Textiles Enterprises
echo Input: LT_TEXT_LTOR_0RAW.csv
echo Output: LT_TEXT_INLT_1ENR.csv, LT_TEXT_INLT_2COL.csv
echo ==============================================================================

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" crawlmail\enrich_infolt_lt_text.py
) else (
    python crawlmail\enrich_infolt_lt_text.py
)

echo.
echo Process completed. Press any key to exit.
pause >nul

