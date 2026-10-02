---
name: data-standards
description: >-
  Bộ quy chuẩn cốt lõi bắt buộc về định dạng dữ liệu, chuẩn hóa số điện thoại, làm sạch email,
  chế độ trình duyệt trực quan và cơ chế lưu trữ an toàn trong toàn bộ workspace.
---

# Quy Chuẩn Cốt Lõi Về Dữ Liệu & Trình Duyệt (Data Standards)

Bộ quy chuẩn này áp dụng bắt buộc cho **tất cả** các script cào dữ liệu, làm giàu dữ liệu và xuất file trong workspace.

---

## 1. Định Dạng File: CSV ONLY (Tuyệt Đối Không Excel)
- **KHÔNG BAO GIỜ** tạo, sử dụng hoặc xuất các file Excel (`.xlsx`, `.xls`) khi làm việc với USER.
- **LUÔN LUÔN** sử dụng định dạng **CSV (`.csv`)** chuẩn mã hóa **UTF-8 with BOM (`utf-8-sig`)** cho tất cả tệp dữ liệu, bảng tính và tệp Cold Mail.
- Mọi script đọc/ghi file CSV phải luôn có `encoding='utf-8-sig'`.

---

## 2. Chuẩn Hóa Số Điện Thoại (Bắt Buộc Nháy Đơn `'`)
- **LUÔN ĐÁNH DẤU NHÁY ĐƠN (`'`)** trước mỗi số điện thoại khi cào data về (ví dụ: `'0912345678`, `'+614...`, `'+47...`).
- Mục đích: Đảm bảo phần mềm bảng tính (Google Sheets, CSV reader) không tự động convert thành dạng số làm mất số `0` ở đầu hoặc lỗi ký tự `+`.
- Cú pháp chuẩn trong Python:
  ```python
  phone = f"'{phone}" if phone and not str(phone).startswith("'") else phone
  ```

---

## 3. Bộ Chấm Điểm Tuyển Chọn 1 Mail Giá Trị Nhất & Lọc Mail Rác (BẮT BUỘC NHƯ SĐT CÓ NHÁY ĐƠN `'`)

> **QUY CHUẨN CỐT LÕI**: Việc thiết lập bộ chấm điểm để giữ lại **DUY NHẤT 1 EMAIL CÓ GIÁ TRỊ NHẤT** cho từng công ty và loại bỏ 100% email rác/template có **tầm quan trọng tuyệt đối ngang hàng với việc thêm dấu nháy đơn `'` trước số điện thoại**. Không bao giờ được phép để sót mail rác hoặc nhét danh sách nhiều mail vào 1 ô gây rối loạn hệ thống Cold Mail.

### A. Lọc bỏ 100% Email Rác & Email Mẫu Template:
- **Làm sạch URL encoding / Ký tự lạ**:
  ```python
  email = urllib.parse.unquote(str(email)).replace('%20', '').strip().lower().rstrip('.,;:')
  ```
- **Loại trừ domain hệ thống, Theme builders & Placeholders**:
  - `sentry.io`, `wix.com`, `wixpress.com`, `wordpress.com`, `squarespace.com`, `weebly.com`, `godaddy.com`, `example.com`, `example.org`, `domain.com`, `yourdomain.com`, `yourcompany.com`, `placeholder.com`, `templatemonster.com`, `themeforest.net`, `bootstrapmade.com`, `schema.org`, `trustpilot.com`, `google.com`.
- **Loại trừ tiền tố hệ thống & Tiền tố mẫu Template**:
  - Tiền tố mẫu của web developer: `youremail`, `your-email`, `your_email`, `yourname`, `your-name`, `yourcompany`, `myemail`, `myname`, `someone`, `nobody`, `john.doe`, `johndoe`, `jane.doe`, `first.last`, `username`, `user`, `sample`, `demo`.
  - Tiền tố hệ thống/tracking: `noreply`, `no-reply`, `donotreply`, `privacy`, `terms`, `cookies`, `gdpr`, `abuse`, `security`, `sentry`, `mailer-daemon`, `test`, `example`.
  - Bộ kết hợp mẫu: `email@email.com`, `mail@domain.com`, `info@yourdomain.com`.
- **Loại bỏ extension file giả mạo email**: `.png`, `.jpg`, `.jpeg`, `.gif`, `.svg`, `.webp`, `.pdf`, `.css`, `.js`, `.woff`.

### B. Thuật Toán Chấm Điểm Heuristic (`score_email_b2b`):
Khi cào được nhiều email trên cùng một website, bắt buộc dùng thuật toán chấm điểm để **CHỌN RA DUY NHẤT 1 EMAIL TỐT NHẤT**:

```python
def score_email_b2b(email, website_domain=""):
    if not email or not isinstance(email, str):
        return -1
    e = email.strip().lower()
    if not EMAIL_REGEX.match(e):
        return -1
    u, d = e.split('@', 1)
    
    # 1. Kiểm tra blacklist
    if d in JUNK_EMAIL_DOMAINS or u in SYSTEM_USERNAMES:
        return -1
    if any(e.endswith(ext) for ext in INVALID_EXTENSIONS):
        return -1

    score = 10
    
    # 2. Điểm cộng trùng Domain Website (+50đ)
    clean_domain = website_domain.lower().replace('www.', '').split('/')[0] if website_domain else ""
    if clean_domain and (clean_domain in d or d in clean_domain):
        score += 50

    # 3. ƯU TIÊN SỐ 1 TUYỆT ĐỐI CHO B2B AGENCY: Nhân sự / Tuyển dụng / Việc làm (+50đ)
    if u in ['praca', 'kariera', 'hr', 'personalne', 'jobs', 'recruitment', 'nabor', 'zamestnanie', 'career', 'careers', 'talent', 'people', 'rekrutacja']:
        score += 50
    # 4. ƯU TIÊN SỐ 2: Ban Giám Đốc / Lãnh đạo điều hành (+45đ)
    elif u in ['vedenie', 'riaditel', 'konatel', 'ceo', 'director', 'manager', 'obchod', 'sales', 'management', 'owner']:
        score += 45
    # 5. ƯU TIÊN SỐ 3: Cổng liên hệ chính thức / Bộ phận thông tin B2B (+40đ)
    elif u in ['info', 'kontakt', 'contact', 'office', 'biuro', 'sekretariat', 'recepcia', 'kancelaria', 'mail']:
        score += 40
    # 6. Email đích danh cá nhân theo domain riêng (+25đ)
    elif '.' in u and score >= 60:
        score += 25
    # 7. Webmail miễn phí (+10đ - chỉ nhận nếu không có mail domain riêng)
    elif d in ['gmail.com', 'seznam.cz', 'zoznam.sk', 'post.sk', 'azet.sk']:
        score += 10
    # 8. Email kỹ thuật / hỗ trợ chung / kế toán (+5đ)
    elif u in ['support', 'admin', 'help', 'webmaster', 'servis', 'faktury', 'uctaren']:
        score += 5

    return score
```

### C. Quy Chuẩn Xuất File:
- Cột `Email` trong CSV: Luôn lấy `max(found_emails, key=lambda e: score_email_b2b(e, domain))`.
- Tuyệt đối chỉ ghi **1 email duy nhất** có điểm cao nhất vào cột `Email`.

---

## 4. Chế Độ Trình Duyệt: TẮT HEADLESS MẶC ĐỊNH (`headless=False`)
- Khi viết script cào hoặc test (Playwright, Selenium...), **LUÔN MẶC ĐỊNH BẬT GIAO DIỆN TRÌNH DUYỆT (`headless=False`)**.
- Mục đích: Giúp USER trực tiếp quan sát tiến độ trực quan, theo dõi trang nạp dữ liệu, nhận biết ngay khi bị Captcha, Cloudflare, hoặc khi selector bị thay đổi.
- Cấu hình kích thước cửa sổ (`viewport` tối thiểu `1280x800` hoặc maximize) để tránh web co về giao diện mobile gây ẩn nút bấm/SĐT.

---

## 5. Lưu Dữ Liệu Tăng Dần & Cơ Chế Checkpoint (Tránh Mất Data)
- **Lưu ngay khi cào được (Incremental Auto-Save / Append)**:
  - Cào được dòng nào hoặc từng đợt nhỏ (batch 3-5 dòng) phải ghi ngay vào file CSV (`mode='a'` kèm `flush()`).
  - **TUYỆT ĐỐI KHÔNG** gom tất cả data vào RAM rồi đợi hết script mới ghi một lần (tránh crash hoặc mất mạng làm mất trắng dữ liệu).
- **Cơ chế Checkpoint / Resume (Cào tiếp không cào lại)**:
  - Script phải hỗ trợ đọc file CSV hiện có hoặc file checkpoint JSON (`progress/progress_*.json` hoặc `cache_*.json`) để tự động bỏ qua các mục đã hoàn thành khi chạy lại.

---

## 6. Chiến Lược Vượt Chặn & Anti-Bot
- **Độ trễ ngẫu nhiên (Human-like Delays)**: Nghỉ ngẫu nhiên giữa các thao tác bấm, cuộn trang.
- **Stealth & User-Agent thật**: Sử dụng User-Agent Chrome máy tính hiện đại, kết hợp `playwright-stealth`.
- **Cuộn trang (Infinite Scroll / Lazy Load)**: Cuộn từng đoạn kèm thời gian chờ DOM nạp đầy đủ.
- **Lọc trùng lặp (Deduplication)**: Kiểm tra trùng theo Số điện thoại, Domain website, hoặc Tên + Địa chỉ.

---

## 7. Bóc Tách Email Đa Tầng (Website + Facebook Crawl) & Bản Địa Hóa
- **QUY TẮC BẮT BUỘC 1: Luôn Tham Khảo Thư Mục `crawlmail/`**:
  - Mọi script cào/làm giàu email PHẢI tham khảo các công cụ và bộ cache có sẵn trong thư mục [`crawlmail/`](file:///d:/glc/nail%20uc/crawlmail/) (như `email_scraper.py`, `enrich_maps_*.py`, cache JSON) để tái sử dụng logic giải mã Cloudflare, regex obfuscated emails, anti-bot và tránh lặp lại bug cũ.
- **QUY TẮC BẮT BUỘC 2: Thiết Kế Bộ Cào Riêng Theo Từng Quốc Gia Mục Tiêu**:
  - Không dùng chung bộ đoán link tiếng Anh một cách mù quáng cho mọi quốc gia.
  - Phải tích hợp trọn bộ từ khóa menu và danh sách subpaths bản địa (ví dụ: Slovakia/Séc là `/kontakt`, `/kontakt.html`, `/kontakty`, `/o-nas`; Đức/Áo là `/kontakt`, `/impressum`; Ba Lan là `/kontakt`, `/o-nas`; Bắc Âu là `/kontakt-oss`...). Xem chi tiết tại [`.agents/skills/crawl-mail/SKILL.md`](file:///d:/glc/nail%20uc/.agents/skills/crawl-mail/SKILL.md).
- **QUY TẮC BẮT BUỘC 3: Đảo Chiều Ưu Tiên Link (Tuyệt Đối Không Để Đoán Mò Chèn Ép Link Thật)**:
  - Thẻ link thực tế `<a href="...">` có trên DOM menu trang chủ chứa từ khóa liên hệ bản địa luôn có **Priority = 10** (cao nhất, duyệt đầu tiên).
  - Danh sách đường dẫn đoán mò chỉ có **Priority = 2** làm phương án dự phòng khi trang chủ ẩn menu hoặc dùng JavaScript.
  - Luôn chuẩn hóa khử trùng lặp trailing slash (`rstrip('/')`) và mở rộng độ sâu quét lên **8–10 subpages**.
- **Quy trình bóc tách đa tầng**:
  - **Tầng 1 (Website Deep Crawl)**: Quét Trang chủ và các trang con liên hệ bản địa hóa theo Priority 10.
  - **Tầng 2 (Bóc tách Link Mạng Xã Hội)**: Tự động gom link Facebook Fanpage (`facebook.com/...`, `fb.com/...`) từ Website.
  - **Tầng 3 (Facebook Email Extraction)**: Trong trường hợp website không công khai email (hoặc chỉ dùng form), tiến hành quét trang giới thiệu / About của Facebook Fanpage để tìm email dự phòng.
  - **Tầng 4 (Ghi nhận nguồn `Email_Source`)**: Luôn lưu cột `Facebook_URL` và `Email_Source` (`Website` hoặc `Facebook`).

---

## 8. Quy Chuẩn File Launcher Batch Script (`.bat`) Trên Windows

Khi tạo file batch launcher (`runners/run_*.bat`) để người dùng nhấp đúp hoặc chạy trong terminal:

1. **Tuyệt Đối KHÔNG Dùng Ký Tự `&` Trần**:
   - Trong Windows `cmd.exe`, `&` là toán tử nối lệnh (command chaining operator).
   - Nếu viết: `title Scraper & Enrichment` hoặc `echo Cào & Làm giàu`, CMD sẽ tách từ sau `&` thành một câu lệnh độc lập để thực thi và văng lỗi:
     `'Enrichment' is not recognized as an internal or external command`
     `'Làm' is not recognized as an internal or external command`
   - **Khắc phục**: Luôn dùng chữ `and`, dấu `+`, hoặc escape bằng dấu mũ `^&`.

2. **Tuyệt Đối KHÔNG Viết Tiếng Việt Có Dấu Trong File `.bat`**:
   - Trình phân tích lệnh của `cmd.exe` trên Windows xử lý các ký tự UTF-8 đa byte (multibyte) rất kém. Khi đọc file batch UTF-8 có dấu tiếng Việt, con trỏ file (seek pointer) bị lệch byte (desync offset).
   - Hậu quả: Các dòng lệnh bên dưới bị nuốt hoặc cắt cụt ký tự đầu tiên, sinh ra hàng loạt lỗi kỳ lạ:
     `'~dp0\.."' is not recognized...` (do `cd /d "%~dp0\.."` bị nuốt mất phần đầu)
     `'aper_rekvizitai.py' is not recognized...` (do `python src\scraper...` bị cắt cụt)
     `'DỮ' is not recognized...`, `'bạ' is not recognized...`
   - **Khắc phục**: Toàn bộ nội dung trong file `.bat` (echo, title, comment, đường dẫn) **BẮT BUỘC dùng tiếng Anh hoặc tiếng Việt KHÔNG DẤU thuần ASCII**.

3. **Luôn Cung Cấp Câu Lệnh Chạy Terminal Cho Người Dùng IDE**:
   - USER chủ yếu làm việc trực tiếp bên trong IDE (Antigravity IDE / VS Code) và sử dụng Terminal tích hợp, không mở Windows File Explorer để nhấp đúp chuột.
   - Do đó, **BẤT CỨ KHI NÀO** tạo mới hoặc đề cập đến file batch launcher (`.bat`), **BẮT BUỘC** phải cung cấp kèm theo câu lệnh chạy trực tiếp trong Terminal:
     * **PowerShell**: `.\runners\<tên_file>.bat` hoặc `cmd /c runners\<tên_file>.bat`
     * **Command Prompt (CMD)**: `runners\<tên_file>.bat`
     * **Lệnh chạy Python trực tiếp tương ứng**: `.venv\Scripts\python.exe <script.py>`



