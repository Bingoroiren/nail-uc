@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Enrich Thit Dan Mach via Virk (DataCVR)
echo ======================================================================
echo    KHOI DONG ENRICH THIT DAN MACH QUA DATACVR.VIRK.DK
echo    Che do: Trinh duyet Chrome truc quan (headless=False)
echo ======================================================================

call .venv\Scripts\activate.bat
python crawlmail\enrich_thit_dan_mach_virk.py

pause
