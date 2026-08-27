@echo off
title Retrying Crawlers (Slovakia, Greece, Australia)
cd /d "%~dp0"

:: Activate the Python Virtual Environment
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
) else (
    echo [WARNING] .venv not found. Running with global python...
)

echo =====================================================================
echo 1/4: Slovakia Recruitment (Slovakia mô giới)
echo =====================================================================
python -u crawlmail/email_scraper.py slovakia_recruitment.csv slovakia_recruitment_with_emails.csv --retry-empty
echo.
echo Formatting Slovakia Recruitment...
python format_sk_emails.py

echo.
echo =====================================================================
echo 2/4: Slovakia Factories (Slovakia nhà máy)
echo =====================================================================
python -u crawlmail/email_scraper.py slovakia_factories.csv slovakia_factories_with_emails.csv --retry-empty
echo.
echo Formatting Slovakia Factories...
python format_sk_factories_emails.py

echo.
echo =====================================================================
echo 3/4: Greece Hotels (Khách sạn Hy Lạp)
echo =====================================================================
python -u crawlmail/email_scraper.py hotel_greece.csv hotel_greece_with_emails.csv --retry-empty
echo.
echo Formatting Greece Hotels...
python format_hotel_gr_emails.py

echo.
echo =====================================================================
echo 4/4: Australia Construction (Xây dựng Úc)
echo =====================================================================
python -u crawlmail/email_scraper.py construction_australia.csv construction_australia_with_emails.csv --retry-empty
echo.
echo Formatting Australia Construction...
python format_construction_au_emails.py

echo.
echo =====================================================================
echo ALL TASKS COMPLETED SUCCESSFULLY!
echo =====================================================================
pause
