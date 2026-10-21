@echo off
chcp 65001 >nul
title Crawler FirmenABC.at (Austria Agency)

cd /d "%~dp0.."

if exist ".venv\Scripts\python.exe" (
    set "PY_CMD=.venv\Scripts\python.exe"
) else (
    set "PY_CMD=python"
)

%PY_CMD% crawlmail\crawl_firmenabc_at.py
pause
