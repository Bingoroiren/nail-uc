@echo off
title Slovakia Construction Cold Mail Formatter
cd /d "%~dp0.."

echo ======================================================
echo    SLOVAKIA CONSTRUCTION COLD MAIL FORMATTER (2COL)
echo    Input:  SK_CONT_STAV_0RAW.csv
echo    Output: SK_CONT_STAV_2COL.csv
echo    Filter: Exclude GDPR/Privacy and Non-Construction
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
python -u formatters/format_sk_cont_stav.py
if errorlevel 1 goto RunFailed

echo.
echo ======================================================
echo    FORMATTING COMPLETED SUCCESSFULLY!
echo    Output 1: SK_CONT_STAV_2COL.csv
echo    Output 2: data/formatted/SK_CONT_STAV_2COL.csv
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
