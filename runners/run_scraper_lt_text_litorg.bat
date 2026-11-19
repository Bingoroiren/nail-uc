@echo off
chcp 65001 >nul
cd /d "%~dp0\.."

echo ==============================================================================
echo [LITORG.CC SCRAPER] Scraping Lithuanian Textiles and Wearing Apparel
echo Source: Catalog 13 (Textiles) and Catalog 14 (Wearing Apparel)
echo ==============================================================================

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" src\scraper_lt_text_litorg.py
) else (
    python src\scraper_lt_text_litorg.py
)

echo.
echo Process completed. Press any key to exit.
pause >nul

