@echo off
title Albania Hotel Web Search and Email Enrichment Launcher
cd /d "%~dp0.."

echo ======================================================================
echo    ALBANIA HOTEL WEB SEARCH ENRICHMENT (WEBSITE AND EMAIL DISCOVERY)
echo ======================================================================
echo.

:: Ensure Python is in PATH if installed locally
if exist "C:\Users\PC\python311\tools\python.exe" (
    set "PATH=C:\Users\PC\python311\tools;C:\Users\PC\python311\tools\Scripts;%PATH%"
)

:: Activate Virtual Environment if it exists
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"
if exist "%~dp0..\.venv\Scripts\activate.bat" call "%~dp0..\.venv\Scripts\activate.bat"

:: Check Python
python --version >nul 2>&1
if errorlevel 1 goto NoPython

if not exist data\raw\hotel_albania.csv goto NoRawData

echo [*] Starting Web Search Enrichment engine...
echo [*] Looking up missing websites, Facebook links, and extracting emails...
echo.
python crawlmail/enrich_web_hotel_albania.py
if errorlevel 1 goto EnrichError

echo.
echo ======================================================================
echo    WEB ENRICHMENT COMPLETED SUCCESSFULLY!
echo    Updated outputs:
echo      - data/formatted/hotel_albania_with_emails_formatted.csv
echo      - Khach san Albania - ColdMail.csv
echo ======================================================================
goto End

:NoPython
echo [-] Error: Python is not installed or not in PATH!
pause
exit /b 1

:NoRawData
echo.
echo [-] Error: File data\raw\hotel_albania.csv not found!
pause
exit /b 1

:EnrichError
echo.
echo [-] Web enrichment encountered an error or was stopped.
pause
exit /b 1

:End
pause
