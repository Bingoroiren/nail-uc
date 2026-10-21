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
- Bắt buộc khai báo bộ lọc `ALLOWED_CATEGORIES` bằng ngôn ngữ địa phương (ví dụ tiếng Anh: `hotel`, `motel`, `hostel`, `resort`, `guest house`, `inn`, `5-star hotel`, `4-star hotel`...; tiếng Hy Lạp, Bồ Đào Nha, Albania tương ứng).
- Bỏ qua các địa điểm có Category không thuộc danh sách cho phép.

---

## 4. Phát Hiện Khách Sạn Đã Đóng Cửa (`Permanently_Closed`)
- Script phải kiểm tra các nhãn đóng cửa đa ngôn ngữ (`Permanently closed`, `Fechado permanentemente`, `Κλειστό οριστικά`...) và lưu vào trường `Permanently_Closed` ('Yes'/'No') để dễ dàng lọc bỏ.

---

## 5. Tiền Xử Lý & Lọc Bỏ Triệt Để Các Trang Đặt Phòng (Pre-crawl OTA & Aggregator Filtering)
Khi tìm Website chính thức và trước khi cào email, **BẮT BUỘC TIỀN XỬ LÝ (PRE-CRAWL FILTER)** để loại bỏ các trang trung gian, tránh cào nhầm email đại lý / support của nền tảng:

1. **Danh sách Nền tảng OTA & Aggregator Phổ Biến**:
   - **OTA toàn cầu**: `booking.com`, `agoda.com`, `airbnb.com`, `expedia.com`, `tripadvisor.com`, `hotels.com`, `trivago.com`, `kayak.com`, `priceline.com`, `hostelworld.com`, `vrbo.com`, `viator.com`, `getyourguide.com`, `makemytrip.com`, `trip.com`, `orbitz.com`, `travelocity.com`, `hotwire.com`, `skyscanner.com`, `opentable.com`.
   - **Affiliates & Booking Aggregators**: `freecancellations.com`, `bluepillow.*`, `placescollective.com`, `highlandhikecottage.eu`, `ocean-vista-lodge.eu`, `brit-voyager.eu`, `backpackinghaven.eu`, `reservation.expert`, `exelentbnb.com`, `linktr.ee`, `yellowpages.*`, `booking.al`, `albania-booking.com`.
   - **Mạng xã hội & Search Engine**: `facebook.com`, `instagram.com`, `linkedin.com`, `youtube.com`, `twitter.com`, `x.com`, `google.com`, `g.co`.

2. **Hàm Chuẩn Hóa Nhận Diện OTA Link**:
   ```python
   def is_ota_or_directory_link(url):
       if not url:
           return True
       url_clean = urllib.parse.unquote(str(url)).strip().lower()
       if not url_clean.startswith(('http://', 'https://')):
           url_clean = f"https://{url_clean}"
       try:
           parsed = urllib.parse.urlparse(url_clean)
           netloc = parsed.netloc.lower().replace('www.', '')
           
           for d in OTA_AND_DIRECTORY_DOMAINS:
               if netloc == d or netloc.endswith(f".{d}"):
                   return True
                   
           path = parsed.path.lower()
           if '/search/' in path or '/search?' in url_clean:
               return True
           if any(x in netloc for x in ['pillow', 'cancellation', 'booking', 'voyager', 'haven', 'lodge', 'reservation']):
               if not any(x in netloc for x in ['hotel', 'resort', 'villa', 'bujtina', 'guest']):
                   return True
       except Exception:
           pass
       return False
   ```

3. **Nguyên Tắc Xử Lý**:
   - **Bỏ qua Request**: Nếu `is_ota_or_directory_link(url)` là `True`, **bỏ qua ngay lập tức, không gửi request HTTP** cào email.
   - **Lọc Domain Email Bổ Sung**: Đưa toàn bộ domain OTA vào danh sách `DISCARD_DOMAINS` để nếu website có nhúng link OTA thì email từ domain đó cũng bị loại bỏ.
   - **Làm Sạch File Xuất**: Nếu khách sạn không có website riêng mà chỉ có link OTA, thay thế cột `Website` / `Liên Hệ` bằng link Google Maps của khách sạn.

---

## 6. Mở Rộng Tiền Tố Email Khách Sạn
- Ngoài các email thông thường (`info@`, `contact@`, `admin@`), bộ quét và làm giàu email phải ưu tiên các tiền tố đặc thù ngành lưu trú:
  - `reservations@...`, `booking@...`, `reception@...`, `frontdesk@...`, `stay@...`, `concierge@...`, `sales@...`, `prenotazioni@...`.
