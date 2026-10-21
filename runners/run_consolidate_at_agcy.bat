@echo off
chcp 65001 >nul
title Consolidate Austria Agency Cold Mail

cd /d "%~dp0.."

if exist ".venv\Scripts\python.exe" (
    set "PY_CMD=.venv\Scripts\python.exe"
) else (
    set "PY_CMD=python"
)

%PY_CMD% crawlmail\consolidate_at_agcy.py
pause
