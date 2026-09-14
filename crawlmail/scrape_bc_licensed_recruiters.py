import os
import sys
import re
import csv
import io
import json
import time
import urllib.parse
import requests
import pypdf
from playwright.async_api import async_playwright
import asyncio

# Ensure UTF-8 on Windows console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ==============================================================================
# DYNAMIC PATH CONFIGURATION
# ==============================================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)

CACHE_FILE = os.path.join(CURRENT_DIR, "cache_bc_recruiters.json")
OUTPUT_CSV_DETAILED = os.path.join(PROJECT_ROOT, "bc_licensed_recruiters_canada.csv")
OUTPUT_CSV_COLDMAIL = os.path.join(PROJECT_ROOT, "bc_licensed_recruiters_coldmail.csv")

TARGET_URL = "https://services.labour.gov.bc.ca/licensing/TFW_IssuancePublication"
BASE_DOMAIN = "https://services.labour.gov.bc.ca"

STANDARD_COLDMAIL_HEADERS = [
    'No.', 'Cong ty', 'Chuc danh', 'Nguoi lien he', 'SDT',
    'Lien He', 'Email', 'Lien He mail', 'Dia chi', 'Luong',
    'Ngay dang', 'Han tuyen', 'Check gui', 'Last Subject',
    'Last Body HTML', 'Trang thai Reply', 'Lan Follow-up',
    'Ngay Follow-up gan nhat', 'Mailbox da dung', 'Category',
    'Link FB'
]

DETAILED_HEADERS = [
    'License #', 'Licensee Name', 'Business Name', 'Email', 'Phone',
    'Address', 'City', 'Country', 'Issuance Date', 'Effective Date',
    'Expiry Date', 'Conditions', 'PDF Link'
]

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[-] Lỗi lưu cache: {e}")

def clean_phone_ca(phone_str):
    if not phone_str:
        return ""
    digits = re.sub(r'[^0-9]', '', phone_str)
    if digits.startswith('1') and len(digits) == 11:
        digits = digits[1:]
    if len(digits) == 10:
        return f"'+1{digits}"
    elif digits:
        return f"'{digits}"
    return ""

def clean_email(email_str):
    if not email_str:
        return ""
    m = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b', email_str)
    return m.group(0).lower().strip('.') if m else ""

def parse_license_pdf_in_memory(pdf_bytes):
    """Bóc tách thông tin từ file PDF nhị phân trong bộ nhớ RAM mà không cần lưu xuống ổ đĩa"""
    info = {
        'license_num': '',
        'phone': '',
        'email': '',
        'address': '',
        'issuance_date': '',
        'effective_date': '',
        'expiry_date': ''
    }
    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        if not reader.pages:
            return info
        txt = reader.pages[0].extract_text()
        if not txt:
            return info

        # 1. License #
        m_lic = re.search(r'License\s*#\s*([A-Za-z0-9-]+)', txt, re.I)
        if m_lic:
            info['license_num'] = m_lic.group(1).strip()

        # 2. Email
        m_em = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b', txt)
        if m_em:
            info['email'] = clean_email(m_em.group(0))

        # 3. Phone (Canada format xxx-xxx-xxxx)
        m_ph = re.search(r'\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b', txt)
        if m_ph:
            info['phone'] = clean_phone_ca(m_ph.group(0))

        # 4. Dates
        m_iss = re.search(r'Issuance date:\s*([^\n\r]+)', txt, re.I)
        if m_iss:
            info['issuance_date'] = m_iss.group(1).strip()

        m_eff = re.search(r'Effective date:\s*([^\n\r]+)', txt, re.I)
        if m_eff:
            info['effective_date'] = m_eff.group(1).strip()

        m_exp = re.search(r'Expiry date:\s*([^\n\r]+)', txt, re.I)
        if m_exp:
            info['expiry_date'] = m_exp.group(1).strip()

        # 5. Address (khối văn bản giữa email và "This certifies that")
        if info['email']:
            escaped_em = re.escape(info['email'])
            m_block = re.search(rf'{escaped_em}\s*\n(.*?)\n\s*This certifies that', txt, re.DOTALL | re.I)
            if m_block:
                lines = [l.strip() for l in m_block.group(1).split('\n') if l.strip()]
                # Bỏ qua dòng tên công ty / carrying on business, giữ lại dòng địa chỉ & mã bưu chính
                addr_lines = []
                for line in lines:
                    if 'carrying on business' in line.lower():
                        continue
                    addr_lines.append(line)
                if addr_lines:
                    info['address'] = ', '.join(addr_lines)

    except Exception as e:
        print(f"      [Lỗi đọc PDF in-memory]: {e}")

    return info

def export_results(all_records):
    """Xuất cả 2 định dạng: Chi tiết và Cold Mail chuẩn 21 cột"""
    # 1. File chi tiết
    with open(OUTPUT_CSV_DETAILED, mode='w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=DETAILED_HEADERS)
        writer.writeheader()
        for r in all_records:
            writer.writerow({
                'License #': r.get('license_num', ''),
                'Licensee Name': r.get('licensee_name', ''),
                'Business Name': r.get('business_name', ''),
                'Email': r.get('email', ''),
                'Phone': r.get('phone', ''),
                'Address': r.get('address', ''),
                'City': r.get('city', ''),
                'Country': r.get('country', ''),
                'Issuance Date': r.get('issuance_date', ''),
                'Effective Date': r.get('effective_date', ''),
                'Expiry Date': r.get('expiry_date', '') or r.get('table_expiry', ''),
                'Conditions': r.get('conditions', ''),
                'PDF Link': r.get('pdf_link', '')
            })

    # 2. File Cold Mail chuẩn (21 cột)
    coldmail_rows = []
    for idx, r in enumerate(all_records, start=1):
        bname = r.get('business_name', '') or r.get('licensee_name', '')
        lname = r.get('licensee_name', '')
        email = r.get('email', '')
        phone = r.get('phone', '')
        full_addr = r.get('address', '')
        if not full_addr:
            full_addr = f"{r.get('city', '')}, {r.get('country', 'Canada')}".strip(', ')
        exp = r.get('expiry_date', '') or r.get('table_expiry', '')
        iss = r.get('issuance_date', '')
        pdf_link = r.get('pdf_link', '')

        coldmail_rows.append({
            'No.': idx,
            'Cong ty': bname,
            'Chuc danh': 'Licensed Foreign Worker Recruiter',
            'Nguoi lien he': lname,
            'SDT': phone,
            'Lien He': pdf_link,
            'Email': email,
            'Lien He mail': '',
            'Dia chi': full_addr,
            'Luong': '',
            'Ngay dang': iss,
            'Han tuyen': exp,
            'Check gui': '',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trang thai Reply': '',
            'Lan Follow-up': '',
            'Ngay Follow-up gan nhat': '',
            'Mailbox da dung': '',
            'Category': 'Licensed Foreign Worker Recruiter (BC, Canada)',
            'Link FB': ''
        })

    with open(OUTPUT_CSV_COLDMAIL, mode='w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=STANDARD_COLDMAIL_HEADERS)
        writer.writeheader()
        writer.writerows(coldmail_rows)

    found_emails = sum(1 for r in all_records if r.get('email'))
    found_phones = sum(1 for r in all_records if r.get('phone'))
    print(f"[*] Checkpoint: {len(all_records)} bản ghi | {found_emails} Email | {found_phones} SĐT")
    print(f"    - File chi tiết: {OUTPUT_CSV_DETAILED}")
    print(f"    - File Cold Mail: {OUTPUT_CSV_COLDMAIL}")

async def crawl_bc_licensed_recruiters():
    print("=" * 70)
    print(" CÀO DỮ LIỆU NHÀ TUYỂN DỤNG LAO ĐỘNG NƯỚC NGOÀI ĐƯỢC CẤP PHÉP (BC, CANADA)")
    print(" [Chế độ: Đọc luồng trực tiếp trên RAM - 0 file PDF lưu xuống ổ đĩa]")
    print("=" * 70)

    cache = load_cache()
    print(f"[*] Đã tải cache: {len(cache)} bản ghi đã lưu")

    extracted_table_records = []

    # BƯỚC 1: Sử dụng Playwright (headless=False) để duyệt qua toàn bộ 20 trang
    async with async_playwright() as p:
        print("\n[*] Khởi động Google Chrome trực quan (headless=False)...")
        browser = await p.chromium.launch(
            headless=False,
            args=["--start-maximized"]
        )
        page = await browser.new_page(viewport={"width": 1280, "height": 850})


        print(f"[*] Đang truy cập: {TARGET_URL}")
        await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        page_num = 1
        max_pages = 25

        while page_num <= max_pages:
            print(f"\n---> Đang đọc Trang {page_num}...")
            
            # Lấy danh sách hàng trong bảng dữ liệu
            rows_data = await page.evaluate("""() => {
                const results = [];
                // Tìm bảng chứa danh sách kết quả
                const trs = Array.from(document.querySelectorAll('table tbody tr'));
                for (const tr of trs) {
                    const tds = Array.from(tr.querySelectorAll('td'));
                    if (tds.length >= 7) {
                        const pdfLinkEl = tr.querySelector('a[href*="TFW_GenerateIssuance"]');
                        const pdfHref = pdfLinkEl ? pdfLinkEl.getAttribute('href') : '';
                        
                        // Lấy text các cột
                        const licensee = tds[1] ? tds[1].innerText.trim() : '';
                        const business = tds[2] ? tds[2].innerText.trim() : '';
                        const city = tds[3] ? tds[3].innerText.trim() : '';
                        const country = tds[4] ? tds[4].innerText.trim() : '';
                        const expiry = tds[5] ? tds[5].innerText.trim() : '';
                        const conditions = tds[6] ? tds[6].innerText.trim() : '';
                        
                        if (licensee === 'View Licence' || !pdfHref) {
                            continue;
                        }
                        
                        if (licensee || business || pdfHref) {
                            results.push({
                                pdf_href: pdfHref,
                                licensee_name: licensee,
                                business_name: business,
                                city: city,
                                country: country,
                                table_expiry: expiry,
                                conditions: conditions
                            });
                        }

                    }
                }
                return results;
            }""")

            print(f"   [+] Trang {page_num}: Thu thập được {len(rows_data)} giấy phép")
            extracted_table_records.extend(rows_data)

            # Kiểm tra nút Next Page
            next_link = page.locator("a[title='Next Page']").first
            has_next = False
            if await next_link.count() > 0:
                is_visible = await next_link.is_visible()
                if is_visible:
                    has_next = True
                    await next_link.click()
                    await page.wait_for_timeout(2500)
                    page_num += 1

            if not has_next:
                print("[*] Đã duyệt đến trang cuối cùng!")
                break

        await browser.close()

    print(f"\n[+] Tổng số giấy phép đã thu thập từ danh sách web: {len(extracted_table_records)}")

    # BƯỚC 2: Tải luồng và đọc nội dung PDF trực tiếp trong bộ nhớ RAM
    print("\n" + "=" * 70)
    print(" BẮT ĐẦU ĐỌC TRỰC TIẾP GIẤY PHÉP TRÊN RAM (IN-MEMORY STREAMING)")
    print(" [Trích xuất Email, SĐT, Địa chỉ, Ngày hết hạn mà không lưu file PDF]")
    print("=" * 70)

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })

    final_records = []
    processed_count = 0

    for item in extracted_table_records:
        processed_count += 1
        href = item.get('pdf_href', '')
        licensee = item.get('licensee_name', '')
        business = item.get('business_name', '')

        if not href:
            final_records.append(item)
            continue

        full_pdf_url = BASE_DOMAIN + href if href.startswith('/') else href
        item['pdf_link'] = full_pdf_url

        # Kiểm tra cache
        if href in cache:
            cached_info = cache[href]
            item.update(cached_info)
            final_records.append(item)
            continue

        print(f"[{processed_count}/{len(extracted_table_records)}] Đang đọc giấy phép: {licensee} ({business})...")
        try:
            res = session.get(full_pdf_url, timeout=15)
            if res.status_code == 200 and res.content.startswith(b'%PDF'):
                pdf_info = parse_license_pdf_in_memory(res.content)
                item.update(pdf_info)
                cache[href] = pdf_info
                
                print(f"   -> 🎯 Email: {pdf_info['email']} | 📞 SĐT: {pdf_info['phone']} | 📅 Hết hạn: {pdf_info['expiry_date'] or item['table_expiry']}")
            else:
                print(f"   [-] Không thể tải PDF (Status: {res.status_code})")
        except Exception as e:
            print(f"   [-] Lỗi kết nối: {e}")

        final_records.append(item)

        # Lưu checkpoint sau mỗi 20 bản ghi
        if processed_count % 20 == 0:
            save_cache(cache)
            export_results(final_records)

        time.sleep(0.1)

    # Lưu kết quả cuối cùng
    save_cache(cache)
    export_results(final_records)

    print("\n" + "=" * 70)
    print(" HOÀN TẤT CÀO DỮ LIỆU BC LICENSED RECRUITERS (CANADA)!")
    print(f" Tổng số hồ sơ: {len(final_records)}")
    print(f" Số lượng Email tìm được: {sum(1 for r in final_records if r.get('email'))}")
    print(f" Số lượng Số điện thoại: {sum(1 for r in final_records if r.get('phone'))}")
    print("=" * 70)

if __name__ == '__main__':
    asyncio.run(crawl_bc_licensed_recruiters())
