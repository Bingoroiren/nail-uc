@echo off
chcp 65001 >nul
title Scraper Belgium Metal Construction and Machining - Pagesdor.be
cd /d "%~dp0\.."

echo ======================================================================
echo    SCRAPER BELGIUM METAL CONSTRUCTION (PAGESDOR.BE)
echo    Category: Constructions metalliques (Gia cong kim loai + Co khi)
echo    URL: https://www.pagesdor.be/entreprises/constructions+m%%C3%%A9talliques/
echo    Output: BE_METL_PDOR_2COL.csv and BE_METL_PDOR_ONLY_EMAILS_READY.csv
echo ======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment python.exe not found at .venv\Scripts\python.exe!
    pause
    exit /b 1
)

echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [*] Starting Belgium metal construction scraper...
echo.

python -u src\scraper_be_metl_pdor.py %*
if errorlevel 1 goto RunFailed

echo.
echo ======================================================================
echo [SUCCESS] Scraping completed successfully!
echo Files updated:
echo  - BE_METL_PDOR_ONLY_EMAILS_READY.csv
echo  - BE_METL_PDOR_2COL.csv
echo  - csdl_mlt\BE_METL_PDOR_ONLY_EMAILS_READY.csv
echo  - archive\be_belgium\BE_METL_PDOR_ONLY_EMAILS_READY.csv
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

