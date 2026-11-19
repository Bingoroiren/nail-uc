@echo off
cd /d "%~dp0\.."

echo ==============================================================================
echo INFO.LT ENRICHMENT - LT WAREHOUSING AND TRANSPORT SUPPORT (LT_WARE_INLT)
echo Input:  LT_WARE_LTOR_0RAW.csv
echo Output: LT_WARE_INLT_1ENR.csv, LT_WARE_INLT_2COL.csv, LT_WARE_INLT_ONLY_EMAILS_READY.csv
echo ==============================================================================

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" crawlmail\enrich_infolt_lt_ware.py %*
) else (
    python crawlmail\enrich_infolt_lt_ware.py %*
)

echo.
echo Process completed. Press any key to exit.
pause >nul

