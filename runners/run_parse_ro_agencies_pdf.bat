@echo off
title Parse Romanian Employment Agency PDFs (Inspectia Muncii and MMSS AMT)
cd /d "%~dp0\.."

echo =======================================================================
echo   ROMANIAN EMPLOYMENT AGENCIES PDF PARSER (RO_AGCY)
echo   Input 1: ro_romania\inspectiamuncii_lista_ag_ian_2025.pdf
echo   Input 2: ro_romania\Reg-Nat-al-AMT-la-31.01.2026.pdf
echo   Output : RO_AGCY_PDF1_0RAW.csv + RO_AGCY_PDF2_0RAW.csv + RO_AGCY_PDF0_0RAW.csv
echo            ro_romania\RO_AGCY_COMPANIES_CUI.csv
echo =======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -c "import pdfplumber, pandas" 2>nul
if errorlevel 1 (
    echo [*] Installing pdfplumber and pandas into .venv...
    ".venv\Scripts\pip.exe" install pdfplumber pandas
)

".venv\Scripts\python.exe" src\parse_ro_agencies_pdf.py
echo.
echo [DONE] Check generated CSV files (UTF-8 with BOM).
pause

