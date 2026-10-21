@echo off
chcp 65001 >nul
title CSDL MLT - Harvest and Consolidate Lithuania Food Industry Data
cd /d "%~dp0\.."

echo =======================================================================
echo   CSDL MLT - LITHUANIA FOOD / MEAT / FISH / DAIRY PORTALS HARVESTER
echo   Target Sources:
echo   - visalietuva.lt (Meat, Fish, Fisheries, Dairy)
echo   - info.lt (Meat, Fish)
echo   - imones.lt (Meat, Fish)
echo   - b2lithuania.com (Sector 17 Exporters)
echo   - rekvizitai.vz.lt (Fisheries and Fish Products)
echo =======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    echo Please install Python virtual environment first.
    pause
    exit /b 1
)

echo [1/5] Harvesting Visalietuva.lt (Meat, Fish, Dairy categories)...
.venv\Scripts\python.exe csdl_mlt\harvest_visalietuva.py

echo.
echo [2/5] Harvesting Info.lt (Meat and Fish categories)...
.venv\Scripts\python.exe csdl_mlt\harvest_infolt.py

echo.
echo [3/5] Harvesting Imones.lt (Meat and Fish categories)...
.venv\Scripts\python.exe csdl_mlt\harvest_imoneslt.py

echo.
echo [4/5] Harvesting B2Lithuania.com API (Sector 17: Food Industry)...
.venv\Scripts\python.exe csdl_mlt\harvest_b2lithuania.py

echo.
echo [5/5] Consolidating, Deduplicating and Deep Email Enriching...
.venv\Scripts\python.exe csdl_mlt\build_master_mlt.py

echo.
echo =======================================================================
echo   ALL HARVESTING AND CONSOLIDATION COMPLETED SUCCESSFULLY!
echo   Output files in: csdl_mlt\
echo   - csdl_mlt\LT_FOOD_WEBD_0RAW.csv (Raw unified)
echo   - csdl_mlt\LT_FOOD_WEBD_1ENR.csv (Enriched, 100%% emails on top)
echo   - LT_FOOD_WEBD_1ENR.csv (Workspace root standard)
echo =======================================================================
pause
