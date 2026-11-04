@echo off
chcp 65001 >nul
title Scraper Belgium Carpenters and Woodworking - Pagesdor.be
cd /d "%~dp0\.."

echo ======================================================================
echo    SCRAPER BELGIUM CARPENTERS AND WOODWORKING (PAGESDOR.BE)
echo    Category: Menuisiers (Cong ty moc + Do go)
echo    URL: https://www.pagesdor.be/entreprises/menuisiers/
echo    Output: BE_WOOD_PDOR_2COL.csv and BE_WOOD_PDOR_ONLY_EMAILS_READY.csv
echo ======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment python.exe not found at .venv\Scripts\python.exe!
    pause
    exit /b 1
)

echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [*] Starting Belgium carpenters scraper...
echo.

python -u src\scraper_be_wood_pdor.py %*
if errorlevel 1 goto RunFailed

echo.
echo ======================================================================
echo [SUCCESS] Scraping completed successfully!
echo Files updated:
echo  - BE_WOOD_PDOR_ONLY_EMAILS_READY.csv
echo  - BE_WOOD_PDOR_2COL.csv
echo  - csdl_mlt\BE_WOOD_PDOR_ONLY_EMAILS_READY.csv
echo  - archive\be_belgium\BE_WOOD_PDOR_ONLY_EMAILS_READY.csv
echo ======================================================================
echo.
pause
goto End

:RunFailed
echo.
echo [ERROR] Scraper encountered an error!
pause
exit /b 1

:End

