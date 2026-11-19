@echo off
chcp 65001 >nul
title Enrich Lithuania Wood and Furniture Data via info.lt (LT_WOOD_INLT)

echo ===============================================================================
echo        ENRICH LITHUANIA WOOD AND FURNITURE ENTERPRISES VIA INFO.LT
echo                  (Source: LT_WOOD_GSEA_1ENR / LT_WOOD_GMAP_1ENR)
echo   Output: LT_WOOD_INLT_1ENR.csv + LT_WOOD_INLT_2COL.csv + READY
echo   Method: FirmCode Direct Match + Obfuscated Email XOR Decode + Proxy Pool
echo ===============================================================================
echo.

cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at .venv\Scripts\python.exe!
    pause
    exit /b 1
)

echo [INFO] Running enrich_infolt_lt_wood.py with Pre-Validated Rotating Proxies...
echo.

.venv\Scripts\python.exe crawlmail\enrich_infolt_lt_wood.py %*
if errorlevel 1 (
    echo.
    echo [ERROR] Enrichment script encountered an error!
    pause
    exit /b 1
)

echo.
echo ===============================================================================
echo [SUCCESS] Lithuania Wood enterprises dataset successfully enriched via info.lt!
echo Data saved to:
echo   - LT_WOOD_INLT_1ENR.csv
echo   - LT_WOOD_INLT_2COL.csv
echo   - LT_WOOD_INLT_ONLY_EMAILS_READY.csv
echo   - Synced to csdl_mlt\ and archive\lt_lithuania\
echo ===============================================================================
echo.
pause

