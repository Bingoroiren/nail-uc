@echo off
title Naver Map Recruiter Email Scraper (Resume/Continue)
cd /d "%~dp0.."

echo ======================================================
echo   RESUMING KOREAN AGENCIES EMAIL CRAWL (format_korean_emails)
echo ======================================================

:: Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 goto NoPython

:: Activate Virtual Environment if it exists
if exist .venv goto ActivateVenv
echo [ERROR] Virtual environment (.venv) not found! Please run run_naver_scraper.bat first to set it up.
pause
exit /b

:ActivateVenv
echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

echo.
echo ======================================================
echo STEP: Launching Email Scraper for Korean Agencies...
echo ======================================================
python formatters/format_korean_emails.py
if errorlevel 1 goto FormatFailed

goto End

:NoPython
echo [ERROR] Python is not installed or not in your PATH.
pause
exit /b

:FormatFailed
echo [ERROR] Email scraping or formatting step failed during execution.
pause
exit /b

:End
echo.
echo ======================================================
echo         EMAIL SCRAPING SESSION TERMINATED
echo ======================================================
pause
