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

## 3. Chuẩn Hóa & Làm Sạch Email
- **Làm sạch URL encoding / Ký tự lạ**:
  - Tự động decode và loại bỏ triệt để `%20` (khoảng trắng mã hóa), `%0A`, `%0D`, khoảng trắng thừa hoặc ký tự rác bám vào email.
  ```python
  email = urllib.parse.unquote(str(email)).replace('%20', '').strip().lower().rstrip('.,;:')
  ```
- **Lọc bỏ email rác & Email mẫu template**:
  - Loại bỏ hoàn toàn email mặc định của template web, theme, framework (`example@example.com`, `user@domain.com`, `yourname@email.com`, `test@...`).
  - Loại bỏ các mail hệ thống không nhận liên hệ trực tiếp (`sentry@...`, `wordpress@...`, `wix@...`, `no-reply@...`, `mailer-daemon@...`).
  - Đảm bảo email đầu ra hợp lệ theo regex chuẩn.

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

## 7. Bóc Tách Email Đa Tầng (Website + Facebook Crawl)
- Khi dữ liệu có trường `Website`:
  - **Tầng 1 (Website Deep Crawl)**: Tự động quét Trang chủ và các trang con liên hệ (`/contact`, `/contacts`, `/kontaktai`, `/apie-mus`, `/careers`, `/karjera`...) để trích xuất email doanh nghiệp chính thức.
  - **Tầng 2 (Bóc tách Link Mạng Xã Hội)**: Tự động tìm kiếm và lưu lại link Facebook Fanpage (`facebook.com/...`, `fb.com/...`) và LinkedIn.
  - **Tầng 3 (Facebook Email Extraction)**: Trong trường hợp website không công khai email (hoặc chỉ dùng form liên hệ), tiến hành quét trang giới thiệu / About của Facebook Fanpage để tìm email dự phòng.
  - **Tầng 4 (Ghi nhận nguồn `Email_Source`)**: Luôn có cột ghi nhận nguồn gốc email (`Website`, `Facebook`, `Directory`) và cột lưu link `Facebook_URL`.

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


