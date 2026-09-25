# Bộ Cào Khách Sạn & Cơ Sở Lưu Trú Albania (Google Maps & Cold Mail)

Hệ thống tự động cào và làm giàu dữ liệu các khách sạn, khu nghỉ dưỡng, biệt thự du lịch và cơ sở lưu trú tại **Albania** trên Google Maps theo đúng quy chuẩn `scrape-hotel` và `data-standards`.

---

## 📌 1. Danh Sách Từ Khóa Lọc (Keywords)
Bộ từ khóa tiếng Albania và quốc tế được tối ưu hóa đặc thù cho ngành lưu trú:
1. `hotel me 4 yje` (Khách sạn 4 sao)
2. `hotel me 3 yje` (Khách sạn 3 sao)
3. `hotel me 2 yje` (Khách sạn 2 sao)
4. `hotel me 5 yje` (Khách sạn 5 sao)
5. `Hotel` (Khách sạn)
6. `Vilë` (Biệt thự nghỉ dưỡng / Villa)
7. `Shtrat & mëngjes` (Bed & Breakfast / B&B)
8. `Ambient pushimi me qira` (Nhà nghỉ / Căn hộ cho thuê du lịch)
9. `Shtëpi për mysafirë` (Guesthouse / Nhà nghỉ)
10. `Homestay` (Homestay / Nhà dân)
11. `Apartament pushues` (Căn hộ dịch vụ du lịch)
12. `Alloggio in famiglia` (Homestay)
13. `Holiday apartment rental` (Căn hộ cho thuê du lịch)
14. `Bujtinë` (Nhà nghỉ truyền thống đặc thù Albania / Bujtinë)
15. `hotel me 1 yje` (Khách sạn 1 sao)

---

## 🧭 2. Cấu Trúc Các Module Hệ Thống

| Module | Tệp tin | Chức năng chính |
| :--- | :--- | :--- |
| **Cấu hình & Từ khóa** | [`src/config_hotel_al.py`](file:///d:/glc/nail%20uc/src/config_hotel_al.py) | Danh sách từ khóa, bộ lọc `ALLOWED_CATEGORIES`, danh sách loại trừ OTA (`booking.com`, `airbnb`...), selector khách sạn. |
| **Tọa độ & Địa điểm** | [`src/locations_al.py`](file:///d:/glc/nail%20uc/src/locations_al.py) | 77 điểm quét và trung tâm du lịch Albania: Tirana, Durrës, Vlorë, Sarandë, Ksamil, Himarë, Theth, Valbonë, Velipojë, Shëngjin... |
| **Engine Cào Maps** | [`src/scraper_hotel_al.py`](file:///d:/glc/nail%20uc/src/scraper_hotel_al.py) | Khử trùng bằng Google Place ID, cuộn feed, lọc OTA, nhận diện đóng cửa, lưu tăng dần (`mode='a'`), checkpoint resume 100%. |
| **Bóc tách Email & Format** | [`formatters/format_hotel_al_emails.py`](file:///d:/glc/nail%20uc/formatters/format_hotel_al_emails.py) | Quét sâu Website tìm email chính chủ, ưu tiên tiền tố khách sạn (`reservations@`, `booking@`, `info@`), chuyển về Template Cold Mail 20 cột. |
| **Launcher 1-Click** | [`runners/run_hotel_al.bat`](file:///d:/glc/nail%20uc/runners/run_hotel_al.bat) | Batch launcher tự động kích hoạt môi trường ảo `.venv`, cài đặt thư viện và chạy tuần tự từ cào đến xuất file. |

---

## ⚙️ 3. Cơ Chế Lưu File Động & Khả Năng Resume 100%

1. **Lưu Tăng Dần (Incremental Auto-Save)**:
   - Dữ liệu được ghi trực tiếp vào CSV (`data/raw/hotel_albania.csv`) ngay khi bóc tách được từng khách sạn (`mode='a'` kèm `f.flush()`). Không bao giờ sợ mất dữ liệu nếu bị ngắt kết nối đột ngột hoặc tắt máy.
2. **Khử Trùng Tuyệt Đối Bằng Google Place ID**:
   - Sử dụng định danh Google Place ID (`0x...:0x...`) thay vì URL động để tránh bị cào lặp lại khi tham số session thay đổi.
3. **Checkpoint & Resume**:
   - Tiến độ quét từng cặp `(địa điểm, từ khóa)` được lưu tại `data/progress/scraping_progress_hotel_al.json`.
   - Nếu bạn tạm dừng hoặc tắt máy, khi mở lại script sẽ tự động nhảy qua các điểm đã quét xong để cào tiếp các điểm còn lại.

---

## 🚀 4. Hướng Dẫn Kéo Về & Chạy Trên Máy Khác

Khi chuyển sang máy tính khác, bạn chỉ cần thực hiện 2 bước đơn giản:

### Bước 1: Kéo code mới nhất từ GitHub
```bash
git pull origin main
```

### Bước 2: Khởi chạy bằng 1 cú nhấp chuột
- Vào thư mục `runners/` và nhấp đúp vào:
  👉 **`runners/run_hotel_al.bat`**
- File `.bat` sẽ tự động:
  1. Tạo môi trường ảo Python `.venv` nếu máy mới chưa có.
  2. Cài đặt các thư viện cần thiết (`requirements.txt`) và Playwright Chromium.
  3. Mở trình duyệt Chrome trực quan (`headless=False`, viewport `1280x800`) để bạn theo dõi và chuông báo `\a` nếu gặp Captcha.
  4. Sau khi cào xong, tự động chạy bóc tách email và xuất file Cold Mail chuẩn.

---

## 📁 5. Kết Quả Đầu Ra

1. **Dữ liệu thô**: `data/raw/hotel_albania.csv`
2. **Dữ liệu chuẩn hóa Cold Mail (20 cột)**:
   - `data/formatted/hotel_albania_with_emails_formatted.csv`
   - `Khách sạn Albania - ColdMail.csv` (Ngay tại thư mục gốc của dự án)
