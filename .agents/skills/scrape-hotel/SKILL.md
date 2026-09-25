---
name: scrape-hotel
description: >-
  Bộ quy chuẩn và kỹ thuật đặc thù khi cào ngành Khách sạn / Lưu trú (Hotel & Lodging) trên Google Maps.
---

# Quy Chuẩn Đặc Thù Cào Khách Sạn / Lưu Trú (Hotel & Lodging)

Google Maps xử lý thực thể Khách sạn (Hotel / Lodging) với giao diện, widget giá, số sao và cấu trúc dữ liệu hoàn toàn khác biệt so với các shop / doanh nghiệp thông thường.

---

## 1. Tránh Trùng Lặp Bằng Google Place ID (Thay Vì URL)
- URL khách sạn trên Google Maps liên tục thay đổi tham số động (ngày nhận/trả phòng, số khách, session token: `?authuser=0&hl=en&rclk=1...`).
- **Bắt buộc trích xuất Place ID** để quản lý danh sách đã cào:
  ```python
  def extract_place_id(url):
      if not url:
          return ""
      match = re.search(r'1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)', url)
      if match:
          return match.group(1).lower()
      return url.split('?')[0].lower()
  ```

---

## 2. Selector Danh Mục Đa Năng & Chờ Tải DOM (Category Selector)
- Khách sạn không dùng thẻ class đơn giản mà phân bổ ở nhiều thẻ kèm số sao:
  ```python
  CATEGORY_SELECTOR = 'span.mgr77e, button.DkEaCc, button.DkEaL, div.F7nice ~ span, div.F7nice ~ button'
  ```
- Phải có vòng lặp chờ trích xuất danh mục (khoảng 10-15 lần lặp x 200ms) để tránh hiện tượng Category bị rỗng do DOM nạp trễ (race condition).

---

## 3. Lọc Danh Mục Nghiêm Ngặt (`ALLOWED_CATEGORIES`)
- Google Maps thường gợi ý lẫn lộn nhà hàng trong khách sạn, quán bar, bãi cắm trại, văn phòng du lịch.
- Bắt buộc khai báo bộ lọc `ALLOWED_CATEGORIES` bằng ngôn ngữ địa phương (ví dụ tiếng Anh: `hotel`, `motel`, `hostel`, `resort`, `guest house`, `inn`, `5-star hotel`, `4-star hotel`...; tiếng Hy Lạp, Bồ Đào Nha tương ứng).
- Bỏ qua các địa điểm có Category không thuộc danh sách cho phép.

---

## 4. Phát Hiện Khách Sạn Đã Đóng Cửa (`Permanently_Closed`)
- Script phải kiểm tra các nhãn đóng cửa đa ngôn ngữ (`Permanently closed`, `Fechado permanentemente`, `Κλειστό οριστικά`...) và lưu vào trường `Permanently_Closed` ('Yes'/'No') để dễ dàng lọc bỏ.

---

## 5. Lọc Bỏ Triệt Để Các Trang Đại Lý Đặt Phòng (OTA Filtering)
- Khi tìm Website chính thức của khách sạn, **BẮT BUỘC LOẠI BỎ CÁC TRANG OTA**:
  - `booking.com`, `agoda.com`, `expedia.com`, `hotels.com`, `tripadvisor.com`, `trivago.com`, `airbnb.com`, `kayak.com`, `hostelworld.com`.
  - Đảm bảo link thu về là Website độc lập do khách sạn trực tiếp sở hữu để quét ra email chính chủ.

---

## 6. Mở Rộng Tiền Tố Email Khách Sạn
- Ngoài các email thông thường (`info@`, `contact@`, `admin@`), bộ quét và làm giàu email phải ưu tiên các tiền tố đặc thù ngành lưu trú:
  - `reservations@...`, `booking@...`, `reception@...`, `frontdesk@...`, `stay@...`, `concierge@...`, `sales@...`.
