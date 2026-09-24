# Workspace Rules & Skills Hub (Antigravity & Gemini)

Hệ thống quy chuẩn và kỹ năng cào / làm giàu dữ liệu tự động cho workspace.

---

## 🧭 Danh Mục Kỹ Năng Chuyên Biệt (`.agents/skills/`)

Toàn bộ các quy trình phức tạp đã được module hóa thành các Skill độc lập:

| Skill | Đường dẫn | Mô tả & Cú pháp kích hoạt |
| :--- | :--- | :--- |
| **`data-standards`** | [`.agents/skills/data-standards/SKILL.md`](file:///d:/glc/nail%20uc/.agents/skills/data-standards/SKILL.md) | **Quy chuẩn cốt lõi**: CSV UTF-8 with BOM (`utf-8-sig`), KHÔNG EXCEL, SĐT luôn có `'`, làm sạch Email `%20`, `headless=False`, lưu tăng dần `mode='a'`. |
| **`scrape-maps`** | [`.agents/skills/scrape-maps/SKILL.md`](file:///d:/glc/nail%20uc/.agents/skills/scrape-maps/SKILL.md) | **Cào Google Maps Đa Quốc Gia**:<br>Kích hoạt: `Tôi muốn cào thị trường [Quốc gia], từ khoá lọc là [X, Y, Z...]`. Tự sinh trọn gói 5 module cào từ A-Z. |
| **`scrape-hotel`** | [`.agents/skills/scrape-hotel/SKILL.md`](file:///d:/glc/nail%20uc/.agents/skills/scrape-hotel/SKILL.md) | **Đặc Thù Ngành Khách Sạn / Lưu Trú**:<br>Khử trùng bằng Google Place ID (`0x...:0x...`), selector Category đa năng kèm wait loop, bộ lọc `ALLOWED_CATEGORIES`, loại bỏ OTA, nhận diện Permanently Closed. |
| **`enrich-maps`** | [`.agents/skills/enrich-maps/SKILL.md`](file:///d:/glc/nail%20uc/.agents/skills/enrich-maps/SKILL.md) | **Làm Giàu Dữ Liệu Bằng Google Maps**:<br>Kích hoạt: `Tôi muốn làm giàu data [tên file CSV hoặc dữ liệu này] bằng ggmap`. So khớp tên nghiêm ngặt, bóc tách SĐT & Web, quét email B2B, lưu tăng dần. |

---

## ⚡ Các Lệnh Kích Hoạt Nhanh (One-Command Triggers)

### 1. Cào thị trường mới trên Google Maps:
> **"Tôi muốn cào thị trường `[Quốc gia]`, từ khoá lọc là `[Từ khoá 1, Từ khoá 2...]`"**  
- Hệ thống tự kích hoạt skill [`scrape-maps`](file:///d:/glc/nail%20uc/.agents/skills/scrape-maps/SKILL.md) (và [`scrape-hotel`](file:///d:/glc/nail%20uc/.agents/skills/scrape-hotel/SKILL.md) nếu là khách sạn), sinh trọn gói:
  1. `src/locations_<country>.py`
  2. `src/config_<industry>_<country>.py`
  3. `src/scraper_<industry>_<country>.py`
  4. `crawlmail/preprocess_csv_*.py` + `formatters/format_*.py`
  5. `runners/run_<industry>_<country>.bat`

### 2. Làm giàu dữ liệu cho file CSV có sẵn:
> **"Tôi muốn làm giàu data `[tên file CSV]` bằng ggmap"**  
- Hệ thống tự kích hoạt skill [`enrich-maps`](file:///d:/glc/nail%20uc/.agents/skills/enrich-maps/SKILL.md), tự đọc cấu trúc CSV, sinh ngay:
  1. Script enrich: `crawlmail/enrich_maps_<dataset>.py`
  2. Launcher 1-Click: `runners/run_enrich_maps_<dataset>.bat`

---

## 📌 Tóm Tắt Quy Chuẩn Cốt Lõi (Áp Dụng Cho Mọi Script)

1. **CSV ONLY**: Tuyệt đối không xuất `.xlsx`/`.xls`. Luôn dùng CSV UTF-8 with BOM (`utf-8-sig`).
2. **SĐT Có Nháy Đơn**: `phone = f"'{phone}" if phone and not phone.startswith("'") else phone`.
3. **Email Sạch**: Decode và loại bỏ triệt để `%20`, loại bỏ email template demo (`example@...`, `sentry@...`, `wix@...`, `no-reply@...`).
4. **Bật Trình Duyệt Thực Tế (`headless=False`)**: Viewport tối thiểu `1280x800` để USER quan sát trực quan tiến độ và dễ dàng xử lý Captcha khi có chuông báo `\a`.
5. **Lưu Tăng Dần (Incremental Auto-Save) & Checkpoint**: Ghi ngay vào CSV sau mỗi vài dòng cào được (`mode='a'` kèm `flush()`) và lưu cache JSON để hỗ trợ Resume 100%, không cào lại từ đầu.
6. **Lọc Trùng Lặp & Loại Trừ Domain Rác**: Lọc bỏ các mạng xã hội và thư bạ (`facebook`, `instagram`, `linkedin`, `google.com/maps`, `yellowpages`, `proff.no`...).
