---
name: scrape-maps
description: >-
  Quy trình tự động thiết lập hệ thống cào Google Maps đa quốc gia theo từ khóa và thị trường.
  Kích hoạt khi người dùng yêu cầu: "Tôi muốn cào thị trường [Quốc gia], từ khoá lọc là [X, Y, Z...]".
---

# Quy Trình Chuẩn: Cào Google Maps Đa Quốc Gia (Google Maps Scraping)

Kỹ năng này chịu trách nhiệm tự động thiết lập trọn gói 5 module cào dữ liệu Google Maps cho bất kỳ thị trường và ngành nghề nào khi người dùng nhắn theo cú pháp:
> **"Tôi muốn cào thị trường [Quốc gia / Thị trường], từ khoá lọc là [X, Y, Z...]"**

---

## 1. Hành Động Tự Động Của Agent

Agent lập tức tạo trọn gói 5 module chuẩn theo cấu trúc dự án:

### Module 1: Tọa Độ Quốc Gia (`src/locations_<country_code>.py`)
- Kiểm tra kho file tọa độ hiện có trong `src/` (`locations_au.py`, `locations_nz.py`, `locations_ca.py`, `locations_ie.py`, `locations_gr.py`, `locations_pt.py`, `locations_fi.py`, `locations_no.py`, `locations_at.py`, `locations_lv.py`, `locations_lt.py`, `locations_sk.py`, `locations_tw.py`, `locations_kr.py`, `locations_al.py`).
- Nếu thị trường mới chưa có: Tự động tạo file chứa danh sách tọa độ (Lat, Lng, Zoom: 13-15) của các thành phố / vùng trọng điểm.

### Module 2: Cấu Hình Chiến Dịch (`src/config_<industry>_<country_code>.py`)
- Khai báo danh sách từ khóa: `KEYWORDS = ["từ khoá 1", "từ khoá 2"]`.
- Đường dẫn file xuất: `OUTPUT_CSV = os.path.join(ROOT_DIR, "data", "raw", "<industry>_<country>.csv")`.
- Cấu hình trình duyệt trực quan: `HEADLESS = False`, `SLOW_MO = 5`, `TIMEOUT = 60000`.
- Bộ SELECTORS chuẩn của Google Maps:
  ```python
  SELECTORS = {
      "results_container": 'div[role="feed"]',
      "listing_link": 'a.hfpxzc',
      "business_name": 'h1.DUwDvf',
      "website": 'a[data-item-id="authority"]',
      "phone": 'button[data-item-id^="phone:tel:"]',
      "address": 'button[data-item-id^="address"]',
      "rating": 'div.F7nice span[aria-hidden="true"]',
      "reviews_count": 'div.F7nice span[aria-label*="reviews"]',
      "category": 'button.DkEaL',
  }
  ```

### Module 3: Engine Cào Google Maps Playwright (`src/scraper_<industry>_<country_code>.py`)
- Playwright Chromium với `headless=False`, viewport tối thiểu `1280x800`.
- Set Geolocation context khớp với tọa độ điểm quét (tránh giật về vị trí Việt Nam).
- Tự động vượt qua cookie/consent banner của Google.
- Cuộn thanh kết quả `div[role="feed"]` nhận diện khi chạm cuối danh sách.
- Trích xuất: Tên, Website, SĐT (bắt buộc thêm dấu nháy đơn `'` ở đầu), Địa chỉ, Rating, Review count, Category, Tọa độ, URL.
- Kiểm tra tính hợp lệ: Bounding box tọa độ / tên nước để tránh cào trôi ra ngoài biên giới.
- **Lưu tăng dần (Incremental Write)**: Ghi ngay vào CSV sau mỗi dòng (`mode='a'`, `encoding='utf-8-sig'`).
- **Checkpoint**: Quản lý qua `progress/progress_<industry>_<country_code>.json` để resume không cào lại.
- **Bắt Captcha**: Hàm `handle_captcha` phát hiện bất thường, dừng an toàn và rung chuông `\a`.

### Module 4: Tiền Xử Lý & Làm Giàu Email (`crawlmail/preprocess_csv_*.py` & `formatters/format_*.py`)
- Lọc bỏ link mạng xã hội / danh bạ trung gian (`facebook`, `instagram`, `linkedin`, `yelp`, `yellowpages`...).
- Quét website tìm email: Decode `%20`, lọc mail demo/template rác (`example@...`, `wix@...`, `sentry@...`).
- Lọc trùng lặp theo Số điện thoại và Domain website.
- Xuất file cuối: `data/formatted/<industry>_<country>_with_emails_formatted.csv`.

### Module 5: Launcher 1-Click (`runners/run_<industry>_<country_code>.bat`)
- Batch script tự động kích hoạt `.venv`, cài dependencies nếu thiếu, cài Playwright Chromium, và chạy tuần tự từ cào thô ➜ lọc ➜ quét mail ➜ xuất CSV cuối.
