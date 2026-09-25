---
name: enrich-maps
description: >-
  Tự động thiết lập quy trình làm giàu dữ liệu (Data Enrichment) cho bất kỳ file CSV nào bằng Google Maps.
  Kích hoạt khi người dùng yêu cầu: "Tôi muốn làm giàu data [tệp CSV hoặc dữ liệu này] bằng ggmap".
---

# Quy Trình Chuẩn: Làm Giàu Dữ Liệu Bằng Google Maps (Company Name Enrichment)

Kỹ năng này quy định quy trình chuẩn để Antigravity tự động phân tích và tạo bộ script làm giàu dữ liệu cho bất kỳ file CSV nào khi người dùng yêu cầu:
> **"Tôi muốn làm giàu data [tệp CSV hoặc dữ liệu này] bằng ggmap"**

---

## 1. Hành Động Tự Động Của Agent Khi Nhận Yêu Cầu

Khi nhận được câu lệnh, Agent **KHÔNG HỎI NHIỀU CÂU HỎI RƯỜM RÀ**, mà lập tức thực hiện 4 bước tự động:

1. **Phân tích cấu trúc file CSV mục tiêu**:
   - Đọc header của file CSV được chỉ định.
   - Tự động nhận diện cột Tên công ty (`name`, `company_name`, `legal_name`, `ten_cty`...).
   - Tự động nhận diện cột Thành phố / Quốc gia (`city`, `municipality`, `address`, `country`...).
   - Tự động nhận diện các cột cần bổ sung: `website`, `phone`, `email`. (Nếu chưa có thì tự động thêm cột vào CSV).
   - Thống kê nhanh số lượng dòng còn thiếu thông tin.

2. **Tạo Script Làm Giàu Dữ Liệu**: `crawlmail/enrich_maps_<dataset_name>.py`
   - Nạp toàn bộ logic chuẩn: So khớp tên nghiêm ngặt, Playwright `headless=False`, bóc tách SĐT nháy đơn `'`, quét website tìm email B2B (loại bỏ `%20`, lọc template rác), lưu tăng dần và cache checkpoint JSON.

3. **Tạo Launcher 1-Click**: `runners/run_enrich_maps_<dataset_name>.bat`
   - Tự động kích hoạt `.venv`, cài dependencies nếu thiếu, mở Chrome trực quan để người dùng quan sát.

4. **Báo cáo kết quả và sẵn sàng chạy**:
   - Tóm tắt nhanh số lượng dòng cần enrich, các cột đã map, và cung cấp lệnh chạy ngay cho người dùng.

---

## 2. Các Quy Tắc Cốt Lõi Bắt Buộc Trong Script Enrich

Mọi script làm giàu dữ liệu tạo ra đều PHẢI tuân thủ các quy tắc sau:

### A. Thuật toán so khớp tên nghiêm ngặt (Strict Name Matching)
- **Không phân biệt hoa thường (`lower()`)**.
- **Khớp giống hệt (Exact Match)**: Tên trên Google Maps trùng hoàn toàn với từ khóa tìm kiếm (sau khi bỏ dấu ngoặc kép rác và khoảng trắng thừa).
- **Quy tắc dấu phân cách (Delimited Variants)**:
  - Nếu kết quả Google Maps có thêm từ/cụm từ (chi nhánh, địa danh, ngành nghề), **BẮT BUỘC** phần mở rộng đó phải nằm sau hoặc trong dấu ngăn cách chuẩn:
    * `-`, `–`, `—`, `|`, `/`, `:`, `,`
    * `(...)`, `[...]`
  - **TỪ CHỐI NGAY LẬP TỨC (Reject)** nếu tên bị chèn từ mới vào giữa hoặc nối liền không có dấu phân tách (tránh nhầm lẫn sang công ty khác).

```python
def is_valid_name_match(query_name, candidate_name, legal_forms=None):
    if not query_name or not candidate_name:
        return False, "EMPTY"
    
    q_raw = re.sub(r'["\'„“”«»]', '', query_name).strip().lower()
    c_raw = re.sub(r'["\'„“”«»]', '', candidate_name).strip().lower()

    if q_raw == c_raw:
        return True, "EXACT"

    # Dấu ngoặc () hoặc []
    c_nobrackets = re.sub(r'\(.*?\)|\[.*?\]', '', c_raw).strip()
    if q_raw == c_nobrackets:
        return True, "BRACKET_MATCH"

    # Dấu ngăn cách phân tách
    parts = [p.strip() for p in re.split(r'[-–—|/:,]', c_raw) if p.strip()]
    if any(p == q_raw for p in parts):
        return True, "DELIMITER_MATCH"

    return False, "NO_MATCH"
```

### B. Chuẩn hóa Số điện thoại:
- Luôn thêm dấu nháy đơn (`'`) ở đầu:
  ```python
  phone = f"'{phone}" if phone and not phone.startswith("'") else phone
  ```

### C. Lọc Website chính thức:
- Loại bỏ 100% link mạng xã hội và sàn danh bạ (`facebook.com`, `instagram.com`, `linkedin.com`, `youtube.com`, `google.com`, `proff.no`, `brreg.no`, `yellowpages`, `wikipedia`...).

### D. Quét & Làm sạch Email B2B:
- Quét trang chủ và các subpage liên hệ (`/contact`, `/kontakt`, `/about`, `/om-oss`...).
- Giải mã Cloudflare email (`data-cfemail`), regex chuẩn, loại bỏ triệt để `%20` và khoảng trắng thừa.
- Lọc bỏ mail hệ thống/template rác (`example@...`, `sentry@...`, `wix@...`, `no-reply@...`).
- Chấm điểm ưu tiên email liên hệ chính (`post@`, `kontakt@`, `info@`, `office@`...).

### E. Vận hành an toàn & Trực quan:
- **`headless=False`**: Luôn mở Chrome trực quan để người dùng theo dõi tiến độ thực tế.
- **Xử lý Captcha**: Rung chuông `\a`, in cảnh báo và tạm dừng chờ người dùng bấm giải Captcha trên trình duyệt rồi nhấn Enter tiếp tục.
- **Lưu tăng dần (Incremental Auto-Save)**: Ghi trực tiếp vào file CSV sau mỗi cụm 3-5 dòng cào được và ghi Cache JSON sau mỗi dòng.
- **Resume 100%**: Đọc cache JSON cũ để tự động bỏ qua các công ty đã xử lý, không bao giờ cào lại từ đầu.
