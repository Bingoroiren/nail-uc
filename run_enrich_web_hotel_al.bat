@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist "C:\Users\PC\python311\tools\python.exe" (
    set "PATH=C:\Users\PC\python311\tools;C:\Users\PC\python311\tools\Scripts;%PATH%"
)
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
)

call "%~dp0runners\run_enrich_web_hotel_al.bat" %*
