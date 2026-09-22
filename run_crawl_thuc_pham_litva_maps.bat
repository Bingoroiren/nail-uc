@echo off
chcp 65001 >nul
title Cao Du Lieu Doanh Nghiep Thuc Pham Litva (Google Maps hl=lt + Chrome)

echo ===========================================================================
echo   BỘ CÀO DOANH NGHIỆP CHẾ BIẾN THỰC PHẨM & NGÀNH THỰC PHẨM LITVA (LITHUANIA)
echo   - Nguồn: Google Maps (hl=lt)
echo   - Trình duyệt: Google Chrome (ggchrome)
echo   - Mức zoom: 11z
echo   - Lọc 22 Tag chuẩn tiếng Litva + Dịch nghĩa Tiếng Việt
echo   - Tự động cào Email & SĐT trực tiếp từ Website
echo   - Bỏ qua các công ty đã có Email trong file Rekvizitai cũ
echo   - Lưu dữ liệu động tức thì (CSV UTF-8-BOM + Excel) chống mất dữ liệu
echo ===========================================================================
echo.

cd /d "%~dp0"

if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "src\scraper_thuc_pham_lt.py"
) else if exist ".\.venv\Scripts\python.exe" (
    ".\.venv\Scripts\python.exe" "src\scraper_thuc_pham_lt.py"
) else (
    python "src\scraper_thuc_pham_lt.py"
)

echo.
echo ===========================================================================
echo   TIẾN TRÌNH ĐÃ HOÀN TẤT HOẶC ĐÃ LƯU TRẠNG THÁI TIẾN ĐỘ THÀNH CÔNG!
echo ===========================================================================
pause
