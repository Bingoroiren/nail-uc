---
name: crawl-mail
description: >-
  Hệ thống bóc tách email doanh nghiệp đa tầng, tối ưu hóa theo ngôn ngữ và thị trường mục tiêu.
  Bắt buộc tham khảo thư mục crawlmail/ để kế thừa logic, tránh bỏ sót email 1 cách vô nghĩa.
---

# Kỹ Năng Bóc Tách Email Đa Tầng Theo Quốc Gia Mục Tiêu (Crawl Mail)

> **Mục tiêu**: Tối đa hóa tỷ lệ tìm thấy email liên hệ chính thức của doanh nghiệp trên Website và Mạng xã hội, tuyệt đối không để xảy ra tình trạng website có email mà scraper quét không ra do sai sót thứ tự duyệt link hoặc thiếu từ khóa ngôn ngữ bản địa.

---

## 🧭 Quy Tắc Vàng 1: Luôn Tham Khảo & Kế Thừa Thư Mục `crawlmail/`

Mọi tác vụ cào email mới, sửa lỗi quét email hoặc làm giàu email:
1. **BẮT BUỘC duyệt qua thư mục [`crawlmail/`](file:///d:/glc/nail%20uc/crawlmail/)**:
   - `crawlmail/email_scraper.py`: Core Playwright scraper hỗ trợ resume, đa luồng concurrency, anti-bot stealth.
   - `crawlmail/enrich_maps_*.py`: Các mẫu enrich sâu kết hợp Google Maps + Website + Facebook.
   - `crawlmail/cache_*.json`: Hơn 30 file cache đã lưu hàng trăm nghìn domain và email đã giải mã thành công.
2. **Kế thừa & Tái sử dụng**:
   - Tái sử dụng cơ chế giải mã Cloudflare `data-cfemail`.
   - Tái sử dụng regex Obfuscated email (`[at]`, `[dot]`).
   - Tái sử dụng danh sách lọc bỏ domain rác (`sentry`, `wix`, `wordpress`, `example.com`...).
   - **TUYỆT ĐỐI KHÔNG** viết code từ đầu một cách chắp vá dẫn đến lặp lại các bug cũ.

---

## ⚡ Quy Tắc Vàng 2: Thứ Tự Ưu Tiên Duyệt Trang Con (Subpages Priority)

**LỖI NGUY HIỂM NHẤT TRƯỚC ĐÂY**: Cho danh sách "đoán mò" tiếng Anh (`/contact`, `/about`) ưu tiên cao hơn link thực tế trên website, dẫn đến việc scraper quét 6 link đoán mò lỗi 404 rồi dừng, bỏ qua hoàn toàn link thật như `kontakt.html`!

### Quy chuẩn phân cấp Priority bắt buộc:

| Mức Độ Ưu Tiên | Nguồn Link | Tiêu Chí Nhận Diện | Hành Động Của Scraper |
| :---: | :--- | :--- | :--- |
| **Priority 10**<br>*(Cao nhất)* | **Link Thật Trên Menu / DOM Trang Chủ** | Thẻ `<a href="...">` có chữ hoặc href chứa từ khóa **Liên hệ bản địa** (`kontakt`, `contact`, `o-nas`...). | **BẮT BUỘC DUYỆT ĐẦU TIÊN**. Nếu website có menu liên hệ, scraper phải vào ngay trang này. |
| **Priority 5** | **Link Thật Dịch Vụ / Đội Ngũ** | Thẻ `<a>` chứa từ khóa thứ cấp (`sluzby`, `services`, `team`, `help`, `cennik`...). | Duyệt tiếp theo nếu trang liên hệ chưa có email. |
| **Priority 2**<br>*(Dự phòng)* | **Đường Dẫn Đoán Mò Bản Địa (Guess Paths)** | Các đường dẫn phổ biến của quốc gia đó (`/kontakt`, `/kontakt.html`, `/impressum`...). | **CHỈ DÙNG KHI** trang chủ không có thẻ `<a>` (web dùng JavaScript ẩn menu). |
| **Priority 1** | **Link Nội Bộ Khác** | Mọi link nội bộ cùng domain. | Duyệt sau cùng nếu còn hạn ngạch. |

---

## 🌍 Quy Tắc Vàng 3: Thiết Kế Bộ Từ Khóa & Đường Dẫn Phù Hợp Từng Quốc Gia

Mỗi thị trường mục tiêu có ngôn ngữ và cấu trúc web đặc thù. Khi cấu hình bộ cào cho quốc gia nào, **BẮT BUỘC** áp dụng trọn gói bộ từ khóa và subpaths sau:

### 1. Slovakia (`.sk`) & Séc (`.cz`):
- **Keywords**: `kontakt`, `kontakty`, `napiste`, `o-nas`, `onas`, `sluzby`, `kariera`, `cennik`, `spolocnost`
- **Subpaths**:
  ```python
  [
      '/kontakt', '/kontakt.html', '/kontakt.php',
      '/kontakty', '/kontakty.html', '/kontakty.php',
      '/o-nas', '/o-nas.html', '/onas.html',
      '/napiste-nam', '/kariera', '/cennik'
  ]
  ```

### 2. Đức (`.de`), Áo (`.at`), Thụy Sĩ (`.ch`):
- **Keywords**: `kontakt`, `impressum`, `ueber-uns`, `wir-ueber-uns`, `anfahrt`, `karriere`, `team`, `standort`
- **Subpaths**:
  ```python
  [
      '/kontakt', '/kontakt.html', '/kontakt.php',
      '/impressum', '/impressum.html', '/impressum.php',
      '/ueber-uns', '/ueber-uns.html', '/karriere', '/anfahrt'
  ]
  ```

### 3. Na Uy (`.no`), Đan Mạch (`.dk`), Thụy Điển (`.se`):
- **Keywords**: `kontakt`, `kontakt-oss`, `kontakt-os`, `om-oss`, `om-os`, `om`, `karriere`, `ansatte`, `finn-oss`
- **Subpaths**:
  ```python
  [
      '/kontakt', '/kontakt-oss', '/kontakt-os',
      '/om-oss', '/om-os', '/om', '/karriere', '/ansatte'
  ]
  ```

### 4. Ba Lan (`.pl`):
- **Keywords**: `kontakt`, `o-nas`, `o-firmie`, `kariera`, `napisz-do-nas`, `dojazd`
- **Subpaths**:
  ```python
  [
      '/kontakt', '/kontakt.html', '/kontakt.php',
      '/o-nas', '/o-nas.html', '/o-firmie', '/kariera'
  ]
  ```

### 5. Pháp (`.fr`), Bỉ (`.be`):
- **Keywords**: `contact`, `nous-contacter`, `a-propos`, `mentions-legales`, `equipe`, `rejoignez-nous`
- **Subpaths**:
  ```python
  [
      '/contact', '/contact.html', '/contact.php',
      '/nous-contacter', '/a-propos', '/mentions-legales'
  ]
  ```

### 6. Tây Ban Nha (`.es`), Bồ Đào Nha (`.pt`), Brazil (`.br`):
- **Keywords**: `contacto`, `contato`, `sobre-nos`, `quienes-somos`, `quem-somos`, `fale-conosco`, `equipo`
- **Subpaths**:
  ```python
  [
      '/contacto', '/contacto.html', '/contato', '/contato.html',
      '/sobre-nos', '/quienes-somos', '/fale-conosco'
  ]
  ```

### 7. Hy Lạp (`.gr`):
- **Keywords**: `epikoinonia`, `epikoinoniste`, `sxetika`, `επικοινων`, `σχετικα`, `επικοινωνια`
- **Subpaths**:
  ```python
  [
      '/epikoinonia', '/epikoinonia.html', '/contact',
      '/sxetika-me-emas', '/about-us'
  ]
  ```

### 8. Các Nước Baltic: Litva (`.lt`), Latvia (`.lv`), Estonia (`.ee`):
- **Keywords**: `kontaktai`, `apie-mus`, `kontakti`, `par-mums`, `kontaktid`, `meist`
- **Subpaths**:
  ```python
  [
      '/kontaktai', '/apie-mus', '/kontakti', '/par-mums', '/kontaktid'
  ]
  ```

### 9. Quốc Tế / Tiếng Anh (Global):
- **Keywords**: `contact`, `contact-us`, `about`, `about-us`, `get-in-touch`, `reach-us`, `locations`
- **Subpaths**:
  ```python
  [
      '/contact', '/contact-us', '/contact.html',
      '/about', '/about-us', '/about.html', '/get-in-touch'
  ]
  ```

---

## 🛠️ Quy Chuẩn Kỹ Thuật Khi Triển Khai Code Scraper

### 1. Chuẩn Hóa & Khử Trùng Lặp URL (Normalize Trailing Slashes)
Tránh việc `/contact` và `/contact/` tính thành 2 lượt truy vấn:
```python
clean_sub = sub_url.rstrip('/')
if clean_sub not in [u.rstrip('/') for u in unique_sub_urls] and clean_sub != base_url.rstrip('/'):
    unique_sub_urls.append(sub_url)
```

### 2. Mở Rộng Độ Sâu Quét Lên 8–10 Trang Con
- Nhiều website đặt link liên hệ ở cấp menu con (chẳng hạn `Dịch vụ -> Đặt hẹn -> Liên hệ`).
- Cấu hình duyệt tối thiểu `8` đến `10` subpages theo thứ tự điểm priority giảm dần:
```python
for sub_url in unique_sub_urls[:8]:
    # Visit subpage, scroll to bottom, extract emails
    if found_emails:
        break  # Dừng ngay khi đã có email chính thức
```

### 3. Bóc Tách Đa Nguồn Trong Mỗi Trang
- **Mailto link**: `a[href^="mailto:"]` -> bỏ phần query `?subject=...`.
- **Cloudflare email**: Giải mã hex bằng phép XOR `decode_cloudflare_email()`.
- **HTML Entities & Obfuscation**: Giải mã `&#64;`, `&#x40;`, `%40` và các mẫu `name [at] domain [dot] com`.
- **Body text & Raw HTML Regex**: Bắt email trong cả văn bản hiển thị lẫn code nguồn ẩn.

### 4. Hệ Thống Chấm Điểm Email B2B Tuyển Chọn 1 Mail Giá Trị Nhất (BẮT BUỘC NHƯ SĐT CÓ NHÁY ĐƠN `'`)
> **TẦM QUAN TRỌNG TỐI THƯỢNG**: Quy tắc chấm điểm để **chỉ giữ lại 1 email giá trị nhất cho mỗi công ty** và loại bỏ 100% email rác/template là **quy chuẩn bắt buộc số 1 ngang hàng với quy tắc thêm dấu nháy đơn `'` trước số điện thoại**. Tuyệt đối không được bỏ qua.

```python
def score_email_b2b(email, website_domain=""):
    """
    Chấm điểm email để chọn ra duy nhất 1 email có giá trị B2B cao nhất.
    Trả về -1 nếu là mail rác, mail template hoặc extension giả mạo.
    """
    if not email or not isinstance(email, str):
        return -1
    e = email.strip().lower()
    if not EMAIL_REGEX.match(e):
        return -1
    u, d = e.split('@', 1)
    
    # 1. Lọc bỏ 100% rác hệ thống & Template / Demo
    if d in JUNK_EMAIL_DOMAINS or any(d.endswith('.' + jd) for jd in JUNK_EMAIL_DOMAINS):
        return -1
    if u in SYSTEM_USERNAMES or u in TEMPLATE_USERNAMES:
        return -1
    if any(p.search(u) for p in TEMPLATE_USERNAME_PATTERNS):
        return -1
    if any(k in u for k in ['youremail', 'your-email', 'yourname', 'your-name']):
        return -1
    if u in ['email', 'mail'] and d in ['email.com', 'mail.com', 'domain.com', 'company.com']:
        return -1
    if any(e.endswith(ext) for ext in INVALID_EXTENSIONS):
        return -1

    score = 10
    
    # 1. Trùng domain website (+50đ)
    clean_domain = website_domain.lower().replace('www.', '').split('/')[0] if website_domain else ""
    if clean_domain and (clean_domain in d or d in clean_domain):
        score += 50

    # 2. ƯU TIÊN SỐ 1 TUYỆT ĐỐI CHO B2B AGENCY: Bộ phận Nhân sự / Tuyển dụng / Việc làm (+50đ)
    # Trúng đích 100% người có nhu cầu tiếp nhận lao động, phỏng vấn và sắp xếp công việc!
    if u in ['praca', 'kariera', 'hr', 'personalne', 'jobs', 'recruitment', 'nabor', 'zamestnanie', 'career', 'careers', 'talent', 'people', 'rekrutacja']:
        score += 50
    # 3. ƯU TIÊN SỐ 2: Ban Giám Đốc / Lãnh đạo điều hành (+45đ)
    # Người có thẩm quyền cao nhất phê duyệt và ký kết hợp đồng cung ứng nhân lực quốc tế!
    elif u in ['vedenie', 'riaditel', 'konatel', 'ceo', 'director', 'manager', 'obchod', 'sales', 'management', 'owner']:
        score += 45
    # 4. ƯU TIÊN SỐ 3: Cổng liên hệ chính thức / Bộ phận thông tin B2B (+40đ)
    # Hòm thư chính thức tiếp nhận thông tin đối tác và chuyển tiếp nội bộ đến phòng nhân sự!
    elif u in ['info', 'kontakt', 'contact', 'office', 'biuro', 'sekretariat', 'recepcia', 'kancelaria', 'mail']:
        score += 40
    # 5. Tên nhân viên đích danh theo domain riêng (+25đ)
    elif '.' in u and score >= 60:
        score += 25
    # 6. Webmail miễn phí (+10đ - chỉ nhận nếu không có mail domain riêng)
    elif d in ['gmail.com', 'seznam.cz', 'zoznam.sk', 'post.sk', 'azet.sk']:
        score += 10
    # 7. Mail kỹ thuật / hỗ trợ chung / kế toán (+5đ - ít liên quan đến tuyển dụng)
    elif u in ['support', 'admin', 'help', 'webmaster', 'servis', 'faktury', 'uctaren']:
        score += 5

    return score

def select_best_email(found_emails, website_domain=""):
    """Chỉ chọn ra duy nhất 1 email có điểm số cao nhất."""
    valid_emails = [e for e in set(found_emails) if score_email_b2b(e, website_domain) > 0]
    if not valid_emails:
        return ""
    return max(valid_emails, key=lambda e: score_email_b2b(e, website_domain))
```


---

## 🔄 Quy Trình Fallback 3 Tầng Khi Website Không Có Email

1. **Tầng 1 (Website Subpages)**: Quét trang chủ + 8 trang con bản địa hóa theo Priority 10.
2. **Tầng 2 (Mạng Xã Hội)**: Tự động gom link Facebook Fanpage (`facebook.com/...`) từ Website. Nếu Website không có mail (chỉ có form), truy cập trang About của Fanpage bằng User-Agent desktop/Googlebot để bóc tách email.
3. **Tầng 3 (Google Maps)**: Nếu cả Website và Facebook đều không có, truy vấn Google Maps Place Panel để lấy email hoặc số điện thoại bổ sung.
