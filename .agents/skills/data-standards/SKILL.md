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
