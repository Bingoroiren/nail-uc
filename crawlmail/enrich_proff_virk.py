import os
import sys
import re
import csv
import json
import time
import shutil
import asyncio
import urllib.parse
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# Đảm bảo hiển thị UTF-8 trên Windows console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ==============================================================================
# CẤU HÌNH ĐƯỜNG DẪN & FILE
# ==============================================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)

INPUT_CSV = os.path.join(PROJECT_ROOT, "proff_arbejdskrafts_tjenester.csv")
BACKUP_CSV = os.path.join(PROJECT_ROOT, "proff_arbejdskrafts_tjenester_backup.csv")
OUTPUT_ENRICHED_CSV = os.path.join(PROJECT_ROOT, "proff_arbejdskrafts_tjenester_enriched.csv")
OUTPUT_COLD_MAIL_CSV = os.path.join(PROJECT_ROOT, "proff_arbejdskrafts_tjenester_cold_mail.csv")
CACHE_FILE = os.path.join(CURRENT_DIR, "cache_proff_virk.json")
USER_DATA_DIR = os.path.abspath(os.path.join(PROJECT_ROOT, "chrome_user_data", "virk_profile"))

# Chuẩn 21 cột Cold Mail
STANDARD_FIELDNAMES = [
    'No.', 'Cong ty', 'Chuc danh', 'Nguoi lien he', 'SDT',
    'Lien He', 'Email', 'Lien He mail', 'Dia chi', 'Luong',
    'Ngay dang', 'Han tuyen', 'Check gui', 'Last Subject',
    'Last Body HTML', 'Trang thai Reply', 'Lan Follow-up',
    'Ngay Follow-up gan nhat', 'Mailbox da dung', 'Category',
    'Link FB'
]

# Regex tìm kiếm Email
EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b')

# ==============================================================================
# HÀM BỔ TRỢ XỬ LÝ DỮ LIỆU
# ==============================================================================
def clean_cvr(raw_cvr):
    """Chuẩn hóa CVR về đúng 8 chữ số"""
    if not raw_cvr:
        return ""
    digits = re.sub(r'[^0-9]', '', str(raw_cvr).strip())
    return digits if len(digits) == 8 else ""

def clean_phone_dk(phone_str):
    """
    Chuẩn hóa số điện thoại Đan Mạch:
    - Định dạng quốc tế +45
    - Thêm dấu nháy đơn đầu dòng "'" cho Excel / Google Sheets
    """
    if not phone_str:
        return ""
    s = str(phone_str).strip().lstrip("'").strip()
    digits = re.sub(r'[^0-9]', '', s)
    if not digits:
        return ""
    if digits.startswith("0045"):
        digits = digits[4:]
    elif digits.startswith("45") and len(digits) >= 10:
        digits = digits[2:]
    
    if len(digits) == 8:
        return f"'+45{digits}"
    elif len(digits) > 8 and len(digits) <= 10:
        return f"'+45{digits[-8:]}"
    return f"'+{digits}" if digits else ""

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[!] Không thể đọc cache: {e}")
    return {}

def save_cache(cache):
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[!] Lỗi lưu cache: {e}")

def extract_virk_data(html_content):
    """Trích xuất email, phone, người quản lý, địa chỉ từ HTML trang chi tiết Virk"""
    data = {
        'phone': '',
        'email': '',
        'cvr': '',
        'manager': '',
        'address': '',
        'status': '',
        'branche': ''
    }
    soup = BeautifulSoup(html_content, 'html.parser')
    text_all = soup.get_text(separator=' ', strip=True)

    # 1. CVR-nummer
    cvr_match = re.search(r'CVR-nummer\s*[:]?\s*([0-9]{8})', text_all)
    if cvr_match:
        data['cvr'] = cvr_match.group(1)

    # 2. Status công ty
    status_match = re.search(r'Status\s*[:]?\s*([A-Za-zæøåÆØÅ ]+)', text_all)
    if status_match:
        data['status'] = status_match.group(1).strip()

    # 3. Quét các hàng thông tin thuộc tính (div.row)
    for row in soup.find_all('div', class_='row'):
        row_text = row.get_text(separator=' | ', strip=True)

        # Điện thoại
        if 'Telefon' in row_text and not data['phone']:
            m = re.search(r'Telefon\s*\|\s*([+0-9 ]+)', row_text)
            if m:
                data['phone'] = clean_phone_dk(m.group(1))

        # Email chính thức
        if ('Mail' in row_text or 'Email' in row_text) and not data['email']:
            m = EMAIL_REGEX.search(row_text)
            if m:
                em = m.group(0).lower().replace('%20', '').strip()
                if not any(em.endswith(x) for x in ['.png', '.jpg', '.jpeg', '.svg', '.webp']):
                    data['email'] = em

        # Địa chỉ
        if 'Adresse' in row_text and not data['address']:
            parts = [p.strip() for p in row_text.split('|') if p.strip()]
            if len(parts) > 1:
                data['address'] = parts[-1]

    # Fallback tìm Email trong toàn bộ HTML (loại bỏ domain hệ thống của Virk/Cloudflare)
    if not data['email']:
        all_emails = EMAIL_REGEX.findall(html_content)
        clean_m = [
            e.lower().replace('%20', '').strip()
            for e in all_emails
            if not any(x in e.lower() for x in [
                '.png', '.jpg', '.jpeg', '.svg', '.webp',
                'virk.dk', 'erhvervsstyrelsen.dk', 'sentry', 'wix', 'cloudflare'
            ])
        ]
        if clean_m:
            data['email'] = clean_m[0]

    # 4. Người quản lý / Ban giám đốc (Direktion / Bestyrelse / Ejer)
    for h in soup.find_all(['h2', 'h3', 'h4', 'strong', 'span']):
        txt = h.get_text(strip=True)
        if any(k in txt for k in ['Direktion', 'Foreningsrepræsentant', 'Ejer', 'Bestyrelse', 'Tegningsberettigede']):
            parent = h.find_parent('div')
            if parent:
                for line in parent.get_text().split('\n'):
                    line = line.strip()
                    if line and not any(k in line for k in [
                        'Direktion', 'Foreningsrepræsentant', 'Indtrådt', 'Tiltrådt',
                        'Ejer', 'Bestyrelse', 'Cookies', 'CVR', 'Tegningsberettigede'
                    ]):
                        if len(line) < 60 and not re.search(r'[0-9]{4}', line):
                            data['manager'] = line
                            break
            if data['manager']:
                break

    return data

def export_results(rows, cache):
    """
    Xuất 2 file kết quả:
    1. proff_arbejdskrafts_tjenester_enriched.csv (Đầy đủ tất cả các cột gốc + dữ liệu Virk)
    2. proff_arbejdskrafts_tjenester_cold_mail.csv (Chuẩn 21 cột Cold Mail để gửi email tự động)
    """
    enriched_rows = []
    cold_mail_rows = []

    for r in rows:
        cvr = clean_cvr(r.get('cvr', ''))
        cached = cache.get(cvr, {})

        # Ưu tiên email và sđt từ Virk nếu có
        virk_email = cached.get('email', '').strip()
        final_email = virk_email or r.get('email', '').strip()

        virk_phone = cached.get('phone', '').strip()
        final_phone = virk_phone or r.get('phone', '').strip()
        if final_phone and not final_phone.startswith("'"):
            final_phone = f"'{final_phone}"

        virk_manager = cached.get('manager', '').strip()
        final_manager = virk_manager or r.get('contact_name', '').strip()

        virk_addr = cached.get('address', '').strip()
        final_addr = virk_addr or r.get('address', '').strip()

        # Tạo row enriched đầy đủ
        en_row = dict(r)
        en_row['email'] = final_email
        en_row['phone'] = final_phone
        en_row['contact_name'] = final_manager
        if virk_addr:
            en_row['address'] = final_addr
        en_row['cvr_status'] = cached.get('status', '')
        en_row['has_email'] = 'OK' if final_email else ''
        enriched_rows.append(en_row)

        # Tạo row chuẩn 21 cột Cold Mail
        cname = r.get('name', '').strip() or r.get('legal_name', '').strip()
        cold_mail_rows.append({
            'No.': 0, # Sẽ gán index sau khi sort
            'Cong ty': cname,
            'Chuc danh': r.get('contact_role', '').strip() or 'Direktør',
            'Nguoi lien he': final_manager,
            'SDT': final_phone,
            'Lien He': r.get('website', '').strip() or r.get('proff_url', '').strip(),
            'Email': final_email,
            'Lien He mail': '',
            'Dia chi': final_addr,
            'Luong': '',
            'Ngay dang': '',
            'Han tuyen': '',
            'Check gui': 'OK' if final_email else '',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trang thai Reply': '',
            'Lan Follow-up': '',
            'Ngay Follow-up gan nhat': '',
            'Mailbox da dung': '',
            'Category': 'Arbejdskrafts tjenester',
            'Link FB': ''
        })

    # Sắp xếp các công ty có Email lên hàng đầu tiên
    enriched_rows.sort(key=lambda x: (x.get('has_email') != 'OK'))
    cold_mail_rows.sort(key=lambda x: (x.get('Check gui') != 'OK'))

    for i, cr in enumerate(cold_mail_rows, 1):
        cr['No.'] = i

    # Ghi file 1: Enriched CSV
    try:
        if enriched_rows:
            fnames = list(enriched_rows[0].keys())
            with open(OUTPUT_ENRICHED_CSV, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fnames)
                writer.writeheader()
                writer.writerows(enriched_rows)
    except Exception as e:
        print(f"[!] Lỗi ghi file enriched CSV: {e}")

    # Ghi file 2: Cold Mail CSV
    try:
        with open(OUTPUT_COLD_MAIL_CSV, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=STANDARD_FIELDNAMES)
            writer.writeheader()
            writer.writerows(cold_mail_rows)
    except Exception as e:
        print(f"[!] Lỗi ghi file cold mail CSV: {e}")

# ==============================================================================
# HÀM CHÍNH ENRICH QUA VIRK (DATACVR)
# ==============================================================================
async def main():
    print("=" * 75)
    print("    BỘ LỌC TRÙNG & ENRICH EMAIL QUA DATACVR.VIRK.DK CHO PROFF.DK")
    print("    Nguồn: proff_arbejdskrafts_tjenester.csv")
    print("    Chế độ: Trình duyệt trực quan (headless=False) - Tối ưu vượt Cloudflare")
    print("=" * 75)

    if not os.path.exists(INPUT_CSV):
        print(f"[!] Không tìm thấy file đầu vào: {INPUT_CSV}")
        return

    # Backup file gốc nếu chưa có
    if not os.path.exists(BACKUP_CSV):
        shutil.copy2(INPUT_CSV, BACKUP_CSV)
        print(f"[+] Đã tạo bản sao lưu file gốc: {BACKUP_CSV}")

    # Đọc dữ liệu đầu vào
    with open(INPUT_CSV, 'r', encoding='utf-8-sig') as f:
        reader = list(csv.DictReader(f))

    print(f"[*] Tổng số dòng dữ liệu đọc được: {len(reader)}")

    # 1. LỌC TRÙNG THEO CVR (Deduplication by CVR)
    unique_rows = []
    seen_cvrs = set()
    dup_count = 0
    empty_cvr_count = 0

    for r in reader:
        raw_cvr = r.get('cvr', '')
        cvr = clean_cvr(raw_cvr)
        if not cvr:
            empty_cvr_count += 1
            continue
        if cvr in seen_cvrs:
            dup_count += 1
            continue
        seen_cvrs.add(cvr)
        unique_rows.append(r)

    print(f"[+] Đã lọc trùng theo CVR:")
    print(f"    - CVR hợp lệ và duy nhất (Unique): {len(unique_rows)}")
    print(f"    - Số dòng trùng CVR đã loại bỏ   : {dup_count}")
    print(f"    - Số dòng thiếu CVR hợp lệ       : {empty_cvr_count}")

    # Đọc cache đã có
    cache = load_cache()
    cached_valid = sum(1 for c in unique_rows if clean_cvr(c.get('cvr')) in cache and cache[clean_cvr(c.get('cvr'))].get('done'))
    print(f"[*] Tiến độ trong cache: {cached_valid} / {len(unique_rows)} CVR đã quét thành công.")

    # Tìm các CVR cần cào
    pending_rows = [
        r for r in unique_rows
        if clean_cvr(r.get('cvr')) not in cache or not cache[clean_cvr(r.get('cvr'))].get('done')
    ]
    print(f"[*] Số lượng CVR còn lại cần tra cứu trên Virk: {len(pending_rows)}")

    if not pending_rows:
        print("[✓] Toàn bộ danh sách CVR đã được enrich trong cache!")
        export_results(unique_rows, cache)
        print(f"[+] Đã cập nhật file kết quả: {OUTPUT_ENRICHED_CSV}")
        print(f"[+] Đã cập nhật file Cold Mail: {OUTPUT_COLD_MAIL_CSV}")
        return

    # Khởi chạy Playwright với persistent profile
    print("\n[*] Đang khởi động trình duyệt trực quan để truy cập DataCVR.virk.dk...")
    os.makedirs(USER_DATA_DIR, exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,
            viewport={"width": 1280, "height": 850},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized"
            ]
        )
        page = context.pages[0] if context.pages else await context.new_page()

        cookie_accepted = False
        processed_count = 0
        total_pending = len(pending_rows)

        for idx, row in enumerate(pending_rows, 1):
            cvr = clean_cvr(row.get('cvr'))
            cname = row.get('name', '').strip() or row.get('legal_name', '').strip()
            virk_url = f"https://datacvr.virk.dk/enhed/virksomhed/{cvr}"

            print(f"\n[{idx}/{total_pending}] 🔍 Tra cứu CVR: {cvr} | {cname}")
            
            extracted = {
                'email': '',
                'phone': '',
                'manager': '',
                'address': '',
                'status': '',
                'done': False
            }

            for attempt in range(3):
                try:
                    resp = await page.goto(virk_url, timeout=35000, wait_until="domcontentloaded")
                    await asyncio.sleep(1.5)

                    # Kiểm tra Cloudflare Challenge
                    title = await page.title()
                    if "just a moment" in title.lower() or "cloudflare" in title.lower():
                        print("   🛑 CLOUDFLARE TURNSTILE PHÁT HIỆN! Chờ tự động vượt hoặc bạn có thể click xác minh trên Chrome...")
                        for _ in range(12):
                            await asyncio.sleep(1.2)
                            t = await page.title()
                            if "just a moment" not in t.lower() and "cloudflare" not in t.lower():
                                break

                    # Chấp nhận Cookie banner một lần đầu
                    if not cookie_accepted:
                        try:
                            cookie_btn = page.locator('button:has-text("Tillad alle"), button:has-text("Accepter alle"), button#onetrust-accept-btn-handler')
                            if await cookie_btn.count() > 0 and await cookie_btn.first.is_visible():
                                await cookie_btn.first.click()
                                cookie_accepted = True
                                await asyncio.sleep(0.8)
                        except Exception:
                            pass

                    # Click nút Accordion "Udvidede virksomhedsoplysninger" để bung thông tin email, sđt chi tiết
                    acc_btn = page.locator('#accordion-udvidede-virksomhedsoplysninger-button, [data-cy="accordion-udvidede-virksomhedsoplysninger"]')
                    if await acc_btn.count() > 0:
                        try:
                            is_exp = await acc_btn.first.get_attribute('aria-expanded')
                            if is_exp != 'true':
                                await acc_btn.first.scroll_into_view_if_needed()
                                await acc_btn.first.click()
                                await asyncio.sleep(1.0)
                        except Exception:
                            pass

                    # Lấy HTML và trích xuất dữ liệu
                    page_html = await page.content()
                    extracted = extract_virk_data(page_html)
                    extracted['cvr_url'] = virk_url
                    extracted['done'] = True

                    email_found = extracted.get('email', '')
                    phone_found = extracted.get('phone', '')
                    mgr_found = extracted.get('manager', '')

                    if email_found:
                        print(f"   🎯 TÌM THẤY EMAIL: {email_found}")
                    else:
                        print(f"   ⚪ Virk không niêm yết email công khai.")

                    if phone_found:
                        print(f"   📞 SĐT: {phone_found}")
                    if mgr_found:
                        print(f"   👤 Đại diện: {mgr_found}")

                    break

                except Exception as e:
                    print(f"   [!] Lỗi kết nối CVR {cvr} (lần {attempt+1}/3): {e}")
                    await asyncio.sleep(2)

            cache[cvr] = extracted
            processed_count += 1

            # Tự động lưu cache và cập nhật file CSV mỗi 5 công ty
            if processed_count % 5 == 0 or idx == total_pending:
                save_cache(cache)
                export_results(unique_rows, cache)
                print(f"   💾 [Checkpoint]: Đã cập nhật cache và 2 file CSV ({processed_count} CVR đã quét)...")

            # Delay an toàn cho VPN tránh bị hạn chế tần suất
            await asyncio.sleep(1.2)

        await context.close()

    # Xuất kết quả lần cuối
    save_cache(cache)
    export_results(unique_rows, cache)

    emails_total = sum(1 for c in unique_rows if cache.get(clean_cvr(c.get('cvr')), {}).get('email') or c.get('email'))
    print("\n" + "=" * 75)
    print("                 HOÀN THÀNH ENRICH QUA VIRK (DATACVR)")
    print("=" * 75)
    print(f"- Tổng số công ty duy nhất đã xử lý : {len(unique_rows)}")
    print(f"- Tổng số công ty có Email hoàn chỉnh: {emails_total} ({(emails_total/len(unique_rows)*100):.1f}%)")
    print(f"- File dữ liệu chi tiết đầy đủ       : {OUTPUT_ENRICHED_CSV}")
    print(f"- File chuẩn 21 cột Cold Mail        : {OUTPUT_COLD_MAIL_CSV}")
    print("=" * 75)

if __name__ == "__main__":
    asyncio.run(main())
