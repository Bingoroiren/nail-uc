@echo off
title Local Path Patcher helper
cd /d "%~dp0.."
set "PATH=C:\Users\PC\python311\tools;%PATH%"

echo ======================================================
echo         PATCHING PYTHON PATHS AND LAUNCHERS
echo ======================================================

:: Run the path patcher python script
python "C:\Users\PC\.gemini\antigravity-ide\brain\98f371e3-6831-4ff3-89bd-6aa3cd327a65\scratch\patch_d_drive_paths.py"
python "C:\Users\PC\.gemini\antigravity-ide\brain\98f371e3-6831-4ff3-89bd-6aa3cd327a65\scratch\patch_bats.py"

echo.
echo [SUCCESS] All paths and launchers have been patched to run locally!
pause
