@echo off
chcp 65001 >nul
title Google Maps Scraper and Enrichment - Lithuania Metal Factories (LT_METL_GMAP)

echo ===============================================================================
echo        GOOGLE MAPS SCRAPER - LITHUANIAN METAL AND FABRICATION FACTORIES
echo                            (LT_METL_GMAP)
echo ===============================================================================
echo   Target: Lithuanian Metalworking, Metal Fabrication, Welding, Foundries
echo   Output: LT_METL_GMAP_0RAW.csv + LT_METL_GMAP_1ENR.csv + LT_METL_GMAP_2COL.csv
echo ===============================================================================
echo.

cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at .venv\Scripts\python.exe!
    pause
    exit /b 1
)

echo CHOOSE AN OPTION:
echo   [1] Run Google Maps Scraper (Raw Collection - LT_METL_GMAP_0RAW.csv)
echo   [2] Run Preprocess and Email Enrichment (Generate 1ENR and 2COL)
echo   [3] Full Pipeline: Scrape + Preprocess + Email Enrichment
echo   [4] Exit
echo.
set /p opt="Enter your choice (1-4) [default: 1]: "

if "%opt%"=="" set opt=1
if "%opt%"=="4" exit /b 0

if "%opt%"=="1" goto RUN_SCRAPER
if "%opt%"=="2" goto RUN_ENRICH
if "%opt%"=="3" goto RUN_PIPELINE

echo Invalid option. Running Scraper by default...
goto RUN_SCRAPER

:RUN_SCRAPER
echo.
echo [1/1] Launching Google Maps Scraper with visible browser...
.venv\Scripts\python.exe src\scraper_metal_lt.py %*
if errorlevel 1 (
    echo.
    echo [ERROR] Scraper encountered an error or was stopped!
    pause
    exit /b 1
)
goto DONE

:RUN_ENRICH
echo.
echo [1/2] Preprocessing and deduplicating raw data...
.venv\Scripts\python.exe crawlmail\preprocess_csv_metal_lt.py
echo.
echo [2/2] Scanning websites for B2B corporate emails and exporting Cold Mail 20-col...
.venv\Scripts\python.exe crawlmail\enrich_maps_lt_metal_engine.py
if errorlevel 1 (
    echo.
    echo [ERROR] Email enrichment encountered an error!
    pause
    exit /b 1
)
goto DONE

:RUN_PIPELINE
echo.
echo [1/3] Step 1: Launching Google Maps Scraper...
.venv\Scripts\python.exe src\scraper_metal_lt.py
if errorlevel 1 (
    echo.
    echo [WARNING] Scraper finished or stopped. Proceeding to enrichment...
)

echo.
echo [2/3] Step 2: Preprocessing and deduplicating raw data...
.venv\Scripts\python.exe crawlmail\preprocess_csv_metal_lt.py

echo.
echo [3/3] Step 3: Scanning websites for corporate emails and formatting Cold Mail...
.venv\Scripts\python.exe crawlmail\enrich_maps_lt_metal_engine.py
if errorlevel 1 (
    echo.
    echo [ERROR] Email enrichment encountered an error!
    pause
    exit /b 1
)
goto DONE

:DONE
echo.
echo ===============================================================================
echo [SUCCESS] Operation completed successfully!
echo Output files:
echo   - LT_METL_GMAP_0RAW.csv (Raw Google Maps dataset)
echo   - LT_METL_GMAP_1ENR.csv (Enriched Master dataset)
echo   - LT_METL_GMAP_2COL.csv (Standard 20-col Cold Mail with 100%% emails on top)
echo   - LT_METL_GMAP_ONLY_EMAILS_READY.csv (Ready cold mail emails)
echo ===============================================================================
echo.
pause

