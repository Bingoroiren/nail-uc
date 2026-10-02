# Workspace Rules & Skills Hub (Antigravity & Gemini)

Hệ thống quy chuẩn và kỹ năng cào / làm giàu dữ liệu tự động cho workspace.

---

## 🧭 Danh Mục Kỹ Năng Chuyên Biệt (`.agents/skills/`)

Toàn bộ các quy trình phức tạp đã được module hóa thành các Skill độc lập:

| Skill | Đường dẫn | Mô tả & Cú pháp kích hoạt |
| :--- | :--- | :--- |
| **`data-standards`** | [`.agents/skills/data-standards/SKILL.md`](file:///d:/glc/nail%20uc/.agents/skills/data-standards/SKILL.md) | **Quy chuẩn cốt lõi**: CSV UTF-8 with BOM (`utf-8-sig`), KHÔNG EXCEL, SĐT luôn có `'`, làm sạch Email `%20`, `headless=False`, lưu tăng dần `mode='a'`. |
| **`crawl-mail`** | [`.agents/skills/crawl-mail/SKILL.md`](file:///d:/glc/nail%20uc/.agents/skills/crawl-mail/SKILL.md) | **Bóc Tách Email Đa Tầng Bản Địa Hóa**:<br>Bắt buộc tham khảo folder `crawlmail/`, ưu tiên thẻ `<a>` thực tế trên DOM (Priority 10), bộ từ khóa/subpaths chuyên biệt từng quốc gia (.sk, .cz, .de, .no, .pl...), tránh bỏ sót email vô nghĩa. |
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

### 3. Cào / Quét lại Email tối ưu theo quốc gia:
> **"Tôi muốn cào/quét email cho `[tên file CSV]`"**
- Hệ thống tự kích hoạt skill [`crawl-mail`](file:///d:/glc/nail%20uc/.agents/skills/crawl-mail/SKILL.md), tham chiếu các module trong `crawlmail/`, áp dụng bộ từ khóa menu + subpaths bản địa của quốc gia đó (`.sk`, `.de`, `.pl`, `.no`...), thiết lập ưu tiên Priority 10 cho link thật trên DOM và quét sâu 8-10 subpages.

---

## 📌 Tóm Tắt Quy Chuẩn Cốt Lõi (Áp Dụng Cho Mọi Script)

1. **CSV ONLY**: Tuyệt đối không xuất `.xlsx`/`.xls`. Luôn dùng CSV UTF-8 with BOM (`utf-8-sig`).
2. **SĐT Có Nháy Đơn**: `phone = f"'{phone}" if phone and not phone.startswith("'") else phone`.
3. **Bộ Chấm Điểm Tuyển Chọn 1 Mail Giá Trị Nhất & Lọc Mail Rác (BẮT BUỘC NHƯ SĐT CÓ NHÁY ĐƠN `'`)**:
   - **Lọc bỏ 100% mail rác/template**: Decode và loại bỏ triệt để `%20`, loại bỏ hoàn toàn email demo/placeholder của theme và web developer (`youremail@...`, `your-email@...`, `yourname@...`, `yourcompany@...`, `someone@...`, `john.doe@...`, `user@domain.com`, `name@...`, `example@...`, `domain@...`, `yourdomain.com`, `email@email.com`), mail hệ thống/tracking (`sentry@...`, `wix@...`, `wixpress@...`, `wordpress@...`, `no-reply@...`, `donotreply@...`, `privacy@...`, `gdpr@...`).
   - **Bắt buộc có hàm chấm điểm (`score_email_b2b`) tối ưu cho B2B Manpower Agency (Môi giới lao động B2B)**: Khi website có nhiều email, **PHẢI CHẤM ĐIỂM ĐỂ GIỮ LẠI DUY NHẤT 1 EMAIL CÓ GIÁ TRỊ NHẤT**:
     * Trùng domain website (+50đ)
     * **Ưu tiên số 1 - Bộ phận Nhân sự / Tuyển dụng / Việc làm**: `praca@`, `kariera@`, `hr@`, `personalne@`, `jobs@`, `recruitment@`, `nabor@`, `career@` (+50đ - trúng đích 100% người tuyển dụng)
     * **Ưu tiên số 2 - Ban Giám Đốc / Lãnh đạo điều hành**: `vedenie@`, `riaditel@`, `konatel@`, `ceo@`, `director@`, `manager@`, `obchod@`, `sales@` (+45đ - người quyết định ký hợp đồng cung ứng)
     * **Ưu tiên số 3 - Cổng liên hệ chính thức / Bộ phận thông tin**: `info@`, `kontakt@`, `contact@`, `office@`, `biuro@`, `sekretariat@`, `recepcia@`, `kancelaria@` (+40đ - đầu mối kết nối B2B chính thức)
     * Email đích danh cá nhân theo domain riêng: `ten.ho@domain.com` (+25đ)
     * Webmail miễn phí: `@gmail.com`, `@seznam.cz`, `@zoznam.sk`... (+10đ, chỉ dùng khi không có mail domain)
     * Email kỹ thuật / hỗ trợ chung / kế toán: `support@`, `admin@`, `servis@`, `faktury@` (+5đ)
     * Email rác / template / crawler trap: 0 điểm (loại bỏ tuyệt đối).
   - Đầu ra cột `Email` trong tệp CSV Cold Mail chỉ được lưu **DUY NHẤT 1 EMAIL TỐI ƯU NHẤT**.
4. **Bật Trình Duyệt Thực Tế (`headless=False`)**: Viewport tối thiểu `1280x800` để USER quan sát trực quan tiến độ và dễ dàng xử lý Captcha khi có chuông báo `\a`.
5. **Lưu Tăng Dần (Incremental Auto-Save) & Checkpoint**: Ghi ngay vào CSV sau mỗi vài dòng cào được (`mode='a'` kèm `flush()`) và lưu cache JSON để hỗ trợ Resume 100%, không cào lại từ đầu.
6. **Lọc Trùng Lặp & Loại Trừ Domain Rác**: Lọc bỏ các mạng xã hội và thư bạ (`facebook`, `instagram`, `linkedin`, `google.com/maps`, `yellowpages`, `proff.no`...).
7. **Bóc Tách Email Đa Tầng Bản Địa Hóa (Tham Khảo `crawlmail/`)**:
   - **Luôn Tham Khảo `crawlmail/`**: Tái sử dụng logic decode Cloudflare, obfuscated regex và cache domain đã giải mã.
   - **Bản Địa Hóa Theo Quốc Gia**: Sử dụng đúng từ khóa menu và subpaths của quốc gia mục tiêu (`kontakt`, `kontakt.html`, `o-nas`, `impressum`, `kontakt-oss`...), bao gồm cả đuôi tĩnh `.html`, `.php`.
   - **Ưu Tiên Link Thật (Priority 10)**: Link tìm thấy trong thẻ `<a>` trên DOM menu luôn được duyệt đầu tiên; đường dẫn đoán mò chỉ có Priority 2 làm dự phòng. Chuẩn hóa khử trùng lặp slash và quét sâu 8–10 trang con.
   - **Fallback Đa Tầng**: Nếu Website không có mail, tự động quét Facebook Fanpage (`facebook.com/...`) và Google Maps.
8. **Quy Chuẩn File Launcher Batch (`.bat`) Trên Windows**:
   - **TUYỆT ĐỐI KHÔNG dùng ký tự `&` trần**: Trong CMD, `&` là toán tử nối lệnh (command chaining). Viết `Scraper & Enrichment` sẽ khiến CMD tách `Enrichment` thành một lệnh độc lập và báo lỗi `'Enrichment' is not recognized`. Hãy dùng `and`, `+` hoặc escape `^&`.
   - **TUYỆT ĐỐI KHÔNG dùng tiếng Việt có dấu trong `.bat`**: Windows CMD xử lý ký tự UTF-8 đa byte (multibyte) làm lệch offset con trỏ đọc file (file seek pointer desync), khiến các dòng lệnh bên dưới bị nuốt/cắt cụt ký tự đầu (ví dụ `python src\...` bị nuốt thành `'aper_...py'`, `cd /d` bị nuốt thành `'~dp0\.."'`). File `.bat` bắt buộc dùng tiếng Anh hoặc tiếng Việt KHÔNG DẤU thuần ASCII.
9. **Luôn Kèm Câu Lệnh Chạy Terminal Cho Người Dùng IDE**:
   - USER làm việc trực tiếp bên trong IDE (Antigravity IDE / VS Code) và chạy qua Terminal tích hợp. Khi tạo file launcher batch (`.bat`) hoặc đề xuất chạy tác vụ, **LUÔN LUÔN** cung cấp sẵn cú pháp lệnh để copy-paste trực tiếp vào Terminal:
     * **PowerShell**: `.\runners\<file>.bat` hoặc `cmd /c runners\<file>.bat`
     * **CMD**: `runners\<file>.bat`
     * **Lệnh Python trực tiếp**: `.venv\Scripts\python.exe <script.py>`

