@echo off
title Austria Agency Cold Mail Formatter
cd /d "%~dp0.."

echo ======================================================
echo    AUSTRIA AGENCY COLD MAIL FORMATTER (2COL)
echo    Input:  AT_AGCY_SHET_1ENR.csv
echo    Output: AT_AGCY_SHET_2COL.csv
echo    Filter: Exclude GDPR/Privacy and Malformed Emails
echo ======================================================

python --version >nul 2>&1
if errorlevel 1 goto NoPython

if exist .venv goto ActivateVenv
echo [*] Error: Virtual environment .venv not found.
pause
exit /b

:ActivateVenv
echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

echo.
echo ======================================================
echo STEP 1: Launching Cold Mail Formatter...
echo ======================================================
python -u formatters/format_at_agcy_shet.py
if errorlevel 1 goto RunFailed

echo.
echo ======================================================
echo    FORMATTING COMPLETED SUCCESSFULLY!
echo    Output 1: AT_AGCY_SHET_2COL.csv
echo    Output 2: data/formatted/AT_AGCY_SHET_2COL.csv
echo ======================================================
pause
goto End

:NoPython
echo [ERROR] Python is not installed or not in your PATH.
pause
exit /b

:RunFailed
echo [ERROR] Formatting failed during execution.
pause
exit /b

:End
