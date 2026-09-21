import os
import sys
import re
import csv
import io
import json
import time
import asyncio
import urllib.parse
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# Đảm bảo in tiếng Việt trên console Windows không bị lỗi font
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)

INPUT_CSV = os.path.join(PROJECT_ROOT, "chế biến thực phẩm litva (danh sách công ty duy nhất).csv")
OUTPUT_CSV = os.path.join(PROJECT_ROOT, "chế biến thực phẩm litva - đã làm giàu rekvizitai.csv")
OUTPUT_XLSX = os.path.join(PROJECT_ROOT, "chế biến thực phẩm litva - đã làm giàu rekvizitai.xlsx")
CACHE_FILE = os.path.join(CURRENT_DIR, "cache_enrich_thuc_pham_litva_rekvizitai.json")
USER_DATA_DIR = os.path.abspath(os.path.join(PROJECT_ROOT, "chrome_user_data", "rekvizitai_profile"))

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
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[!] Lỗi lưu cache: {e}")

def normalize_company_name(name: str) -> str:
    """
    Chuẩn hóa tên công ty để so khớp:
    - Bỏ tiền tố/hậu tố loại hình doanh nghiệp: AB, UAB, MB, IĮ, II, VšĮ, ŽŪB, TŪB, KŪB...
    - Bỏ dấu ngoặc kép, dấu chấm, phẩy, gạch ngang
    - Chuyển thành chữ thường không dấu tiếng Litva
    """
    if not name:
        return ""
    s = name.lower().strip()
    s = re.sub(r'["\'“”„”«»()\[\]]', ' ', s)

    # Loại bỏ các từ định danh loại hình công ty
    patterns = [
        r'\buab\b',
        r'\bab\b',
        r'\bmb\b',
        r'\biį\b',
        r'\bii\b',
        r'\bindividuali įmonė\b',
        r'\bind\. įmonė\b',
        r'\bvšį\b',
        r'\bvsi\b',
        r'\bžūb\b',
        r'\bzub\b',
        r'\bžūk\b',
        r'\bzuk\b',
        r'\btūb\b',
        r'\btub\b',
        r'\bkūb\b',
        r'\bkub\b',
        r'\bkb\b',
        r'\bfilialas\b',
        r'\bfil\b',
        r'\bskerdykla\b',  # một số tên có hậu tố lò mổ
    ]
    for p in patterns:
        s = re.sub(p, ' ', s, flags=re.IGNORECASE)

    # Chuẩn hóa ký tự Litva có dấu về không dấu
    trans_map = str.maketrans({
        'ą': 'a', 'č': 'c', 'ę': 'e', 'ė': 'e', 'į': 'i',
        'š': 's', 'ų': 'u', 'ū': 'u', 'ž': 'z'
    })
    s = s.translate(trans_map)
    s = re.sub(r'[-_.,;:/]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def clean_query_for_search(name: str) -> str:
    """Tạo từ khóa tìm kiếm sạch (bỏ ngoặc kép, bỏ AB, UAB) để đưa vào ô tìm kiếm"""
    if not name:
        return ""
    q = name.strip()
    # Tách dấu phẩy nếu có phần mở rộng (VD: "AB VILKYŠKIŲ PIENINĖ , On behalf of...")
    q = q.split(',')[0].strip()
    q = re.sub(r'["\'“”„”«»]', ' ', q)
    # Bỏ tiền tố đầu dòng
    q = re.sub(r'^(AB|UAB|MB|IĮ|II|VšĮ|VSI|ŽŪB|ZUB)\s+', '', q, flags=re.IGNORECASE).strip()
    # Bỏ hậu tố cuối dòng
    q = re.sub(r'\s+(AB|UAB|MB|IĮ|II|VšĮ|VSI|ŽŪB|ZUB)$', '', q, flags=re.IGNORECASE).strip()
    q = re.sub(r'\s+', ' ', q).strip()
    return q

def extract_rekvizitai_details(html_content: str, target_url: str):
    """Bóc tách dữ liệu chi tiết từ trang hồ sơ doanh nghiệp trên Rekvizitai"""
    data = {
        "company_code": "",
        "vat_code": "",
        "phone": "",
        "email": "",
        "website": "",
        "address": "",
        "city": "",
        "postal_code": "",
        "manager": "",
        "manager_title": "",
        "employees": "",
        "activity": "",
        "rekvizitai_name": "",
        "rekvizitai_url": target_url
    }
    try:
        soup = BeautifulSoup(html_content, 'html.parser')

        # 1. Bóc tách từ textarea sao chép thông tin nhanh
        ta = soup.find('textarea')
        if ta:
            for line in ta.get_text().strip().split('\n'):
                line = line.strip()
                if not line:
                    continue
                if line.startswith('Company:') or line.startswith('Įmonė:'):
                    data['rekvizitai_name'] = re.sub(r'^(Company:|Įmonė:)', '', line).strip()
                elif line.startswith('Address:') or line.startswith('Adresas:'):
                    data['address'] = re.sub(r'^(Address:|Adresas:)', '', line).strip()
                elif line.startswith('Phone:') or line.startswith('Telefonas:'):
                    data['phone'] = re.sub(r'^(Phone:|Telefonas:)', '', line).strip()
                elif line.startswith('Registration code:') or line.startswith('Įmonės kodas:'):
                    data['company_code'] = re.sub(r'^(Registration code:|Įmonės kodas:)', '', line).strip()
                elif line.startswith('VAT:') or line.startswith('PVM kodas:'):
                    data['vat_code'] = re.sub(r'^(VAT:|PVM kodas:)', '', line).strip()
                elif line.startswith('Manager:') or line.startswith('Vadovas:'):
                    m_val = re.sub(r'^(Manager:|Vadovas:)', '', line).strip()
                    parts = [x.strip() for x in m_val.split(',') if x.strip()]
                    if parts:
                        data['manager'] = parts[0]
                    if len(parts) > 1:
                        data['manager_title'] = parts[1]

        # 2. Bóc tách bổ sung từ JSON-LD Schema (Organization)
        for s in soup.find_all('script', type='application/ld+json'):
            if s.string and 'Organization' in s.string:
                try:
                    jd = json.loads(s.string)
                    if not data['rekvizitai_name']:
                        data['rekvizitai_name'] = jd.get('name', '')
                    if not data['vat_code']:
                        data['vat_code'] = jd.get('vatID', '')
                    if not data['website']:
                        data['website'] = jd.get('url', '')
                    emp = jd.get('numberOfEmployees', '')
                    if isinstance(emp, dict):
                        data['employees'] = str(emp.get('value', ''))
                    elif emp:
                        data['employees'] = str(emp)
                    addr = jd.get('address', {})
                    if isinstance(addr, dict):
                        data['city'] = addr.get('addressLocality', '')
                        data['postal_code'] = addr.get('postalCode', '')
                        if not data['address']:
                            data['address'] = f"{addr.get('streetAddress', '')}, {data['postal_code']} {data['city']}".strip(', ')
                    acts = jd.get('knowsAbout', [])
                    if isinstance(acts, list) and acts:
                        data['activity'] = '; '.join(acts)
                except Exception:
                    pass
                break

        # 3. Bóc tách số điện thoại nếu thiếu
        if not data['phone']:
            tel_link = soup.select_one('a[href^="tel:"]')
            if tel_link:
                data['phone'] = tel_link.get_text(strip=True)

        # 4. Bóc tách email
        mail_link = soup.select_one('a[href^="mailto:"]')
        if mail_link:
            raw_mail = mail_link.get('href', '').replace('mailto:', '').split('?')[0].strip()
            data['email'] = urllib.parse.unquote(raw_mail).replace('%20', '').replace(' ', '').strip()

        # 5. Nếu chưa có tên hiển thị, lấy từ h1
        if not data['rekvizitai_name']:
            h1 = soup.find('h1')
            if h1:
                data['rekvizitai_name'] = h1.get_text(strip=True)

    except Exception as e:
        print(f"      [!] Lỗi bóc tách chi tiết: {e}")

    return data

async def enrich_food_lithuania():
    print("=" * 75)
    print("   BỘ LÀM GIÀU THÔNG TIN DOANH NGHIỆP CHẾ BIẾN THỰC PHẨM LITVA")
    print("   Nguồn tra cứu: https://rekvizitai.vz.lt/ (Lithuanian Business Directory)")
    print("   Chế độ: Trình duyệt Chrome trực quan (headless=False)")
    print("=" * 75)

    if not os.path.exists(INPUT_CSV):
        print(f"[!] Không tìm thấy file đầu vào: {INPUT_CSV}")
        return

    with open(INPUT_CSV, "r", encoding="utf-8-sig") as f:
        reader = list(csv.DictReader(f))

    total = len(reader)
    cache = load_cache()
    crawled_count = sum(1 for v in cache.values() if v.get('match_status') == 'MATCH')
    print(f"[*] Tổng số công ty cần tra cứu: {total}")
    print(f"[*] Đã khớp thành công trong cache: {crawled_count} công ty.")

    async with async_playwright() as p:
        print("[*] Đang mở trình duyệt Google Chrome...")
        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            channel="chrome",
            headless=False,
            viewport={"width": 1280, "height": 850},
            args=["--disable-blink-features=AutomationControlled"]
        )
        page = context.pages[0] if context.pages else await context.new_page()

        # 1. Truy cập trang chủ Rekvizitai và kiểm tra xác minh Cloudflare
        print("[*] Đang kết nối tới https://rekvizitai.vz.lt/ ...")
        await page.goto("https://rekvizitai.vz.lt/", timeout=60000)

        passed_cf = False
        print("   [*] Đang kiểm tra bảo vệ Cloudflare...")
        for sec in range(1, 120):
            await asyncio.sleep(1.5)
            try:
                title = await page.title()
            except Exception:
                # Đang chuyển hướng (navigation reload) sau khi xác minh
                await asyncio.sleep(1.5)
                continue

            if "just a moment" in title.lower() or "security verification" in title.lower():
                if sec % 3 == 0:
                    print(f"   🛑 [{sec}s] PHÁT HIỆN CLOUDFLARE TURNSTILE! Vui lòng bấm ô 'Verify you are human' trên màn hình Chrome...")
                continue
            else:
                print(f"\n[+] Vượt qua Cloudflare thành công! Tiêu đề trang: {title}")
                passed_cf = True
                break
        else:
            print("[!] Chưa vượt qua màn hình xác minh sau 120s. Bạn vẫn có thể bấm xác minh bất kỳ lúc nào trên màn hình Chrome.")

        processed_since_save = 0

        # 2. Vòng lặp tra cứu từng công ty
        for idx, row in enumerate(reader, 1):
            raw_name = row.get("ten_cong_ty", "").strip()
            if not raw_name:
                continue

            # Kiểm tra cache
            if raw_name in cache and cache[raw_name].get('match_status') in ['MATCH', 'NO_MATCH', 'NOT_FOUND']:
                continue

            query = clean_query_for_search(raw_name)
            target_norm = normalize_company_name(raw_name)

            print(f"\n[{idx:>3}/{total}] 🔍 Tra cứu: '{raw_name}' (Từ khóa tìm kiếm: '{query}')")

            record_res = {
                "match_status": "NOT_FOUND",
                "rekvizitai_name": "",
                "company_code": "",
                "vat_code": "",
                "phone": "",
                "email": "",
                "website": "",
                "address": "",
                "city": "",
                "postal_code": "",
                "manager": "",
                "manager_title": "",
                "employees": "",
                "activity": "",
                "rekvizitai_url": ""
            }

            try:
                # Tìm ô tìm kiếm
                search_box = page.locator('#search-input, input[name="name"], input#companyName, input[placeholder*="Kas" i], input[placeholder*="įmonė" i], input[type="text"]').first
                if await search_box.count() == 0:
                    # Nếu không thấy ô tìm kiếm, điều hướng lại trang chủ
                    await page.goto("https://rekvizitai.vz.lt/", timeout=25000)
                    await asyncio.sleep(1)
                    search_box = page.locator('#search-input, input[name="name"], input#companyName, input[placeholder*="Kas" i], input[placeholder*="įmonė" i], input[type="text"]').first

                await search_box.fill('')
                await search_box.fill(query)
                await search_box.press('Enter')

                # Chờ trang kết quả tải
                await asyncio.sleep(1.5)

                # Kiểm tra nếu gặp lại Cloudflare
                try:
                    cur_title = await page.title()
                except Exception:
                    cur_title = ""
                if "just a moment" in cur_title.lower():
                    print("   🛑 Gặp xác minh Cloudflare, vui lòng bấm xác minh trên màn hình Chrome...")
                    while True:
                        await asyncio.sleep(1.5)
                        try:
                            t = await page.title()
                            if "just a moment" not in t.lower():
                                break
                        except Exception:
                            continue

                # Thu thập các link công ty trong kết quả
                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')

                candidates = []
                for a in soup.find_all('a', href=True):
                    h = a['href']
                    if ('/imone/' in h or '/en/company/' in h) and not any(x in h for x in ['/report/', '/print/', '/order/', '/login']):
                        name_text = a.get_text(strip=True)
                        if name_text and len(name_text) > 1 and name_text.lower() not in ['plačiau', 'daugiau', 'more', 'view']:
                            full_url = urllib.parse.urljoin('https://rekvizitai.vz.lt', h)
                            clean_url = full_url.split('?')[0].rstrip('/') + '/'
                            candidates.append({'name': name_text, 'url': clean_url})

                # So khớp tên (loại bỏ tiền tố AB, UAB, MB, IĮ...)
                best_match = None
                for cand in candidates:
                    cand_norm = normalize_company_name(cand['name'])
                    # So khớp chính xác 100%
                    if cand_norm == target_norm:
                        best_match = cand
                        break
                    # Hoặc 1 bên là tiền tố chính xác của bên kia
                    elif cand_norm and target_norm and (cand_norm.startswith(target_norm) or target_norm.startswith(cand_norm)):
                        if not best_match:
                            best_match = cand

                if best_match:
                    print(f"   ✅ KHỚP TÊN: '{best_match['name']}' -> Đang mở hồ sơ: {best_match['url']}")
                    record_res['match_status'] = "MATCH"
                    record_res['rekvizitai_name'] = best_match['name']
                    record_res['rekvizitai_url'] = best_match['url']

                    # Mở trang hồ sơ công ty
                    await page.goto(best_match['url'], wait_until="domcontentloaded", timeout=25000)
                    await asyncio.sleep(1)

                    detail_content = await page.content()
                    details = extract_rekvizitai_details(detail_content, best_match['url'])
                    record_res.update(details)
                    record_res['match_status'] = "MATCH"
                    record_res['rekvizitai_name'] = details['rekvizitai_name'] or best_match['name']

                    print(f"      Mã cty: {record_res['company_code']} | VAT: {record_res['vat_code']} | SĐT: {record_res['phone']} | Email: {record_res['email']}")
                else:
                    if candidates:
                        print(f"   ⚪ Tìm thấy {len(candidates)} kết quả nhưng không khớp tên (VD: '{candidates[0]['name']}').")
                        record_res['match_status'] = "NO_MATCH"
                    else:
                        print("   ⚪ Không tìm thấy kết quả nào.")
                        record_res['match_status'] = "NOT_FOUND"

            except Exception as e:
                print(f"   [!] Lỗi khi tra cứu: {e}")

            cache[raw_name] = record_res
            processed_since_save += 1

            # Lưu cache và xuất file định kỳ mỗi 5 công ty
            if processed_since_save >= 5 or idx == total:
                save_cache(cache)
                export_enriched_results(reader, cache)
                processed_since_save = 0

            await asyncio.sleep(0.8)

        # Lưu lần cuối
        save_cache(cache)
        export_enriched_results(reader, cache)
        await context.close()

    print("\n" + "=" * 75)
    print("                 HOÀN THÀNH LÀM GIÀU DỮ LIỆU")
    print("=" * 75)
    print(f"- File CSV kết quả đã làm giàu : {os.path.abspath(OUTPUT_CSV)}")
    if os.path.exists(OUTPUT_XLSX):
        print(f"- File Excel kết quả (.xlsx)    : {os.path.abspath(OUTPUT_XLSX)}")
    print("=" * 75)

def export_enriched_results(reader, cache):
    """Xuất danh sách đã làm giàu ra file CSV và Excel"""
    enriched_rows = []
    for idx, row in enumerate(reader, 1):
        raw_name = row.get("ten_cong_ty", "").strip()
        c_data = cache.get(raw_name, {})

        new_row = {
            "stt": idx,
            "ten_cong_ty": raw_name,
            "trang_thai_khop": c_data.get("match_status", "CHƯA_TRA_CỨU"),
            "ten_chinh_thuc_rekvizitai": c_data.get("rekvizitai_name", ""),
            "ma_so_doanh_nghiep": c_data.get("company_code", ""),
            "ma_so_thue_vat": c_data.get("vat_code", ""),
            "so_dien_thoai": c_data.get("phone", ""),
            "email": c_data.get("email", ""),
            "website": c_data.get("website", ""),
            "nguoi_dai_dien": c_data.get("manager", ""),
            "chuc_vu": c_data.get("manager_title", ""),
            "so_nhan_vien": c_data.get("employees", ""),
            "dia_chi_dang_ky": c_data.get("address", ""),
            "thanh_pho_dang_ky": c_data.get("city", ""),
            "ma_buu_chinh_dang_ky": c_data.get("postal_code", ""),
            "nganh_nghe_dang_ky": c_data.get("activity", ""),
            "rekvizitai_url": c_data.get("rekvizitai_url", ""),
            "ma_phe_duyet_traces": row.get("ma_phe_duyet", ""),
            "so_luong_nganh_cap_phep": row.get("so_luong_nganh_cap_phep", ""),
            "cac_nganh_hoat_dong": row.get("cac_nganh_hoat_dong", ""),
            "cac_hoat_dong_chi_tiet": row.get("cac_hoat_dong_chi_tiet", ""),
            "dia_chi_traces": row.get("dia_chi", ""),
            "thanh_pho_traces": row.get("thanh_pho", ""),
            "vung_tinh_traces": row.get("vung_tinh", ""),
            "quoc_gia": "Lithuania"
        }
        enriched_rows.append(new_row)

    # 1. Xuất CSV UTF-8-SIG
    fieldnames = list(enriched_rows[0].keys())
    with open(OUTPUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(enriched_rows)

    # 2. Xuất Excel XLSX
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Đã làm giàu Rekvizitai"
        ws.views.sheetView[0].showGridLines = True

        ws.append(fieldnames)
        for r in enriched_rows:
            ws.append(list(r.values()))

        header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")

        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")

        for col in ws.columns:
            max_len = 0
            col_letter = col[0].column_letter
            for cell in col[:100]:
                if cell.value:
                    max_len = max(max_len, min(len(str(cell.value)), 45))
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

        wb.save(OUTPUT_XLSX)
    except Exception:
        pass

if __name__ == "__main__":
    asyncio.run(enrich_food_lithuania())
