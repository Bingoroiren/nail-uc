@echo off
chcp 65001 >nul
title Scraper Belgium Slaughterhouses (Abattoirs) - Pagesdor.be
cd /d "%~dp0\.."

echo ======================================================================
echo    SCRAPER BELGIUM SLAUGHTERHOUSES - ABATTOIRS (PAGESDOR.BE)
echo    Category: Abattoirs (Lo mo + Che bien thit)
echo    URL: https://www.pagesdor.be/entreprises/abattoirs/
echo    Output: BE_MEAT_PDOR_2COL.csv and BE_MEAT_PDOR_ONLY_EMAILS_READY.csv
echo ======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment python.exe not found at .venv\Scripts\python.exe!
    pause
    exit /b 1
)

echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [*] Starting Belgium slaughterhouses scraper...
echo.

python -u src\scraper_be_meat_pdor.py %*
if errorlevel 1 goto RunFailed

echo.
echo ======================================================================
echo [SUCCESS] Scraping completed successfully!
echo Files updated:
echo  - BE_MEAT_PDOR_ONLY_EMAILS_READY.csv
echo  - BE_MEAT_PDOR_2COL.csv
echo  - csdl_mlt\BE_MEAT_PDOR_ONLY_EMAILS_READY.csv
echo  - archive\be_belgium\BE_MEAT_PDOR_ONLY_EMAILS_READY.csv
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

