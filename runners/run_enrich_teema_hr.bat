@echo off
chcp 65001 > nul
title TEEMA Taiwan HR & Recruitment Data Enrichment Engine
color 0B

echo ===============================================================================
echo       HỆ THỐNG LÀM GIÀU DỮ LIỆU NHÂN SỰ & TUYỂN DỤNG NHÀ MÁY ĐÀI LOAN
echo   - Nguồn dữ liệu: TEEMA B2B Official + Website Careers & Recruitment Crawl
echo   - Mục tiêu: Bóc tách HR Contact, Chức danh, Email Tuyển dụng & SĐT Bàn nội bộ
echo ===============================================================================
echo.

cd /d "%~dp0\.."

python crawlmail\enrich_teema_hr_data.py

echo.
echo ===============================================================================
echo   Tiến trình làm giàu dữ liệu đã kết thúc!
echo ===============================================================================
pause
