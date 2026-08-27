@echo off
title Git Pull Update Scraper Project
cd /d "%~dp0"
set "PATH=C:\Users\PC\git\cmd;C:\Users\PC\python311\tools;%PATH%"

echo ======================================================
echo         GIT PULL CODE UPDATE (DATA PROTECTED)
echo ======================================================

echo [*] Pulling new code from GitHub...
git pull origin main

if errorlevel 1 (
    echo.
    echo [ERROR] Git pull failed. Please check internet connection or repository permissions.
    pause
    exit /b
)

echo.
echo [*] Re-patching local paths to ensure scripts run locally...
python "C:\Users\PC\.gemini\antigravity-ide\brain\98f371e3-6831-4ff3-89bd-6aa3cd327a65\scratch\patch_d_drive_paths.py"
python "C:\Users\PC\.gemini\antigravity-ide\brain\98f371e3-6831-4ff3-89bd-6aa3cd327a65\scratch\patch_bats.py"

echo.
echo [SUCCESS] Project updated and paths patched successfully!
pause
