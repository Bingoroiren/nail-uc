import sys
import io
import json
import time
import os
import re
import csv
import argparse
import random
import urllib.parse
from curl_cffi import requests

# Đảm bảo in tiếng Việt trên console Windows không bị lỗi font
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

DEFAULT_KEYWORDS = ["Henkilöstövuokraus", "Rekrytointi"]
DEFAULT_CACHE = "crawlmail/cache_finder_fi.json"
OUTPUT_CSV_DEDUP = "finder_fi_henkilostovuokraus_rekrytointi_dedup.csv"
OUTPUT_CSV_ALL = "finder_fi_henkilostovuokraus_rekrytointi_all.csv"
OUTPUT_XLSX = "finder_fi_henkilostovuokraus_rekrytointi.xlsx"

HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'fi,en-US;q=0.9,en;q=0.8',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
}

def extract_next_data(html: str):
    """Trích xuất dữ liệu JSON hydration từ Next.js tag __NEXT_DATA__"""
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except Exception as e:
        print(f"[!] Lỗi parse JSON __NEXT_DATA__: {e}")
        return None

def format_business_id(raw_id: str) -> str:
    """Định dạng Y-tunnus chuẩn Phần Lan: 12345678 -> 1234567-8"""
    if not raw_id:
        return ""
    s = str(raw_id).strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:7]}-{s[7]}"
    return s

def clean_website_url(raw_url: str) -> str:
    """Chuẩn hóa đường dẫn website"""
    if not raw_url:
        return ""
    u = str(raw_url).strip()
    if not u:
        return ""
    if not u.startswith(('http://', 'https://')):
        u = 'https://' + u
    return u.rstrip('/')

def scrape_email_from_website(website_url: str, session: requests.Session) -> str:
    """Cào bổ sung email trực tiếp từ website của công ty nếu Finder không có"""
    if not website_url:
        return ""
    clean_url = clean_website_url(website_url)
    try:
        r = session.get(clean_url, headers=HEADERS, impersonate="chrome124", timeout=7)
        if r.status_code == 200:
            emails = set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', r.text))
            valid = []
            for e in emails:
                le = e.lower()
                if not any(le.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js']):
                    if not any(ign in le for ign in ['sentry', 'example', 'domain', 'noreply', 'no-reply', 'wixpress']):
                        valid.append(e)
            if valid:
                return valid[0]
    except Exception:
        pass
    return ""

def crawl_finder(keywords=DEFAULT_KEYWORDS, cache_file=DEFAULT_CACHE, max_pages_per_kw=None, delay=0.5, deep_email=True):
    print("=" * 75)
    print("   BỘ CÀO DỮ LIỆU TUYỂN DỤNG & CHO THUÊ NHÂN SỰ PHẦN LAN (FINDER.FI)")
    print(f"   Từ khóa: {', '.join(keywords)}")
    print("=" * 75)

    os.makedirs(os.path.dirname(cache_file) if os.path.dirname(cache_file) else '.', exist_ok=True)
    
    # 1. Đọc cache nếu có (khả năng khôi phục / resume)
    cached_all_records = []
    visited_pages = set()
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                cached_all_records = saved.get('records', [])
                visited_pages = set(saved.get('visited_pages', []))
                print(f"[*] Đã tải từ cache: {len(cached_all_records)} bản ghi, {len(visited_pages)} trang đã cào.")
        except Exception as e:
            print(f"[!] Không thể đọc cache: {e}")

    session = requests.Session()
    
    # Dùng dictionary để quản lý trùng lặp theo ID và Y-tunnus
    all_raw_records = list(cached_all_records)

    for kw in keywords:
        print(f"\n" + "-" * 60)
        print(f"[*] BẮT ĐẦU CÀO TỪ KHÓA: '{kw}'")
        print("-" * 60)

        # Lấy trang 1 để kiểm tra tổng số công ty
        first_url = f"https://www.finder.fi/search?what={urllib.parse.quote(kw)}&sort=RELEVANCE_desc&page=1&type="
        
        total_company_hits = 0
        total_pages = 1
        
        for attempt in range(3):
            try:
                r = session.get(first_url, headers=HEADERS, impersonate="chrome124", timeout=20)
                if r.status_code == 200:
                    next_data = extract_next_data(r.text)
                    if next_data:
                        queries = next_data.get('props', {}).get('pageProps', {}).get('dehydratedState', {}).get('queries', [])
                        if queries:
                            q_data = queries[0].get('state', {}).get('data', {})
                            total_dict = q_data.get('total', {})
                            total_company_hits = total_dict.get('company', 0)
                            # Mỗi trang 15 kết quả
                            total_pages = max(1, (total_company_hits + 14) // 15)
                            print(f"[+] Tìm thấy: {total_company_hits} công ty ({total_pages} trang kết quả).")
                            break
            except Exception as e:
                print(f"[!] Lỗi kết nối trang 1 ({kw}): {e}")
                time.sleep(2)
        else:
            print(f"[!] Không thể nạp trang 1 của từ khóa '{kw}'. Bỏ qua.")
            continue

        if max_pages_per_kw and max_pages_per_kw < total_pages:
            total_pages = max_pages_per_kw
            print(f"[*] Giới hạn số trang theo yêu cầu: {total_pages} trang.")

        # Duyệt từng trang của từ khóa
        for p in range(1, total_pages + 1):
            page_key = f"{kw}:{p}"
            if page_key in visited_pages:
                continue

            page_url = f"https://www.finder.fi/search?what={urllib.parse.quote(kw)}&sort=RELEVANCE_desc&page={p}&type="
            success = False

            for attempt in range(3):
                try:
                    res = session.get(page_url, headers=HEADERS, impersonate="chrome124", timeout=20)
                    if res.status_code != 200:
                        time.sleep(1.5)
                        continue

                    next_data = extract_next_data(res.text)
                    if not next_data:
                        time.sleep(1.5)
                        continue

                    queries = next_data.get('props', {}).get('pageProps', {}).get('dehydratedState', {}).get('queries', [])
                    if not queries:
                        break

                    q_data = queries[0].get('state', {}).get('data', {})
                    items = q_data.get('results', [])

                    if not items and p > 1:
                        # Đã hết kết quả
                        break

                    page_added = 0
                    for it in items:
                        contact_type = it.get('contactType', '')
                        # Chỉ lấy công ty và văn phòng đại diện (loại bỏ hồ sơ cá nhân / person)
                        if contact_type not in ['COMPANY', 'OFFICE']:
                            continue

                        cid = str(it.get('id') or '').strip()
                        raw_bid = str(it.get('businessId') or '').strip()
                        y_tunnus = format_business_id(raw_bid)
                        name = it.get('companyOfficialName') or it.get('name') or ''
                        if isinstance(name, dict):
                            name = name.get('name', '')

                        email = str(it.get('companyEmail') or it.get('email') or '').strip()
                        phone = str(it.get('phone') or it.get('mobile') or '').strip()
                        website = clean_website_url(it.get('companyUrl'))

                        # Nếu website phụ có
                        additional_www = it.get('additionalWwwAddresses') or []
                        if not website and additional_www:
                            website = clean_website_url(additional_www[0])

                        # Địa chỉ
                        addr_obj = it.get('address') or {}
                        street = addr_obj.get('streetAddress') or ''
                        postal_code = addr_obj.get('postalCode') or ''
                        city = addr_obj.get('postOffice') or it.get('homeCity') or ''
                        province = it.get('provinceName') or it.get('provinceNameAlias') or ''

                        # Ngành nghề
                        tol_code = it.get('tolMainLineofBusinessCode') or ''
                        tol_name = it.get('tolMainLineofBusinessName') or ''
                        lines = it.get('lineofBusinessNames') or []
                        lines_str = "; ".join(lines)

                        # Tài chính gần nhất
                        fin_list = it.get('financials') or []
                        latest_fin = fin_list[0] if fin_list else {}
                        turnover = latest_fin.get('turnover') or ''
                        employees = latest_fin.get('numberOfEmployees') or ''
                        profit = latest_fin.get('operatingProfit') or ''

                        entry = {
                            "finder_id": cid,
                            "business_id": y_tunnus,
                            "name": name.strip(),
                            "phone": phone,
                            "email": email,
                            "website": website,
                            "address": street.strip(),
                            "postal_code": postal_code.strip(),
                            "city": city.strip(),
                            "province": province.strip(),
                            "keyword": kw,
                            "tol_code": tol_code,
                            "tol_name": tol_name,
                            "line_of_business": lines_str,
                            "company_form": it.get('companyFormFull') or it.get('companyForm') or '',
                            "turnover_k_eur": turnover,
                            "employees": employees,
                            "operating_profit_k_eur": profit,
                            "facebook_url": it.get('facebookUrl') or '',
                            "linkedin_url": it.get('linkedinUrl') or '',
                            "finder_url": f"https://www.finder.fi/yritys/{cid}" if cid else ""
                        }

                        # Nếu có website mà chưa có email, và bật deep_email: cào nhanh email từ website
                        if deep_email and website and not email:
                            found_email = scrape_email_from_website(website, session)
                            if found_email:
                                entry['email'] = found_email

                        all_raw_records.append(entry)
                        page_added += 1

                    visited_pages.add(page_key)
                    success = True
                    print(f"[{kw}] Trang {p:>3}/{total_pages} | +{page_added} công ty | Tổng tích lũy: {len(all_raw_records)}")
                    break

                except Exception as e:
                    time.sleep(1.5)

            if not success:
                print(f"[!] Cảnh báo: Không thể tải trang {p} ({kw}).")

            # Lưu cache và xuất file định kỳ mỗi 10 trang
            if p % 10 == 0 or p == total_pages:
                save_data_and_export(all_raw_records, visited_pages, cache_file)

            time.sleep(delay + random.uniform(0.1, 0.2))

    # Lưu lần cuối và xuất file
    save_data_and_export(all_raw_records, visited_pages, cache_file)

def save_data_and_export(all_raw_records, visited_pages, cache_file):
    """Lưu cache JSON, tiến hành lọc trùng và xuất cả 2 file CSV + Excel"""
    # 1. Lưu cache
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump({
                "visited_pages": list(visited_pages),
                "records": all_raw_records
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[!] Lỗi ghi cache: {e}")

    # 2. Xử lý LỌC TRÙNG (Deduplication)
    # Khóa định danh duy nhất: Mã số doanh nghiệp (business_id) hoặc Tên công ty chuẩn hóa
    dedup_dict = {}
    for r in all_raw_records:
        key = r['business_id'] if r['business_id'] else r['name'].upper().strip()
        if not key:
            continue

        if key not in dedup_dict:
            item = dict(r)
            item['keywords_found'] = r['keyword']
            item['cities'] = [r['city']] if r['city'] else []
            item['offices_count'] = 1
            dedup_dict[key] = item
        else:
            existing = dedup_dict[key]
            # Gộp từ khóa
            if r['keyword'] and r['keyword'] not in existing['keywords_found']:
                existing['keywords_found'] += f"; {r['keyword']}"
            # Gộp thành phố
            if r['city'] and r['city'] not in existing['cities']:
                existing['cities'].append(r['city'])
            existing['offices_count'] += 1
            # Bổ sung thông tin nếu bản ghi trước còn thiếu
            if not existing['email'] and r['email']:
                existing['email'] = r['email']
            if not existing['website'] and r['website']:
                existing['website'] = r['website']
            if not existing['phone'] and r['phone']:
                existing['phone'] = r['phone']
            if not existing['address'] and r['address']:
                existing['address'] = r['address']
            if not existing['turnover_k_eur'] and r['turnover_k_eur']:
                existing['turnover_k_eur'] = r['turnover_k_eur']
            if not existing['employees'] and r['employees']:
                existing['employees'] = r['employees']

    dedup_list = list(dedup_dict.values())
    for it in dedup_list:
        it['cities_all'] = "; ".join(it['cities'])

    # 3. Xuất CSV ĐÃ LỌC TRÙNG
    fieldnames_dedup = [
        "stt",
        "name",
        "business_id",
        "website",
        "email",
        "phone",
        "address",
        "postal_code",
        "city",
        "cities_all",
        "province",
        "keywords_found",
        "offices_count",
        "tol_code",
        "tol_name",
        "line_of_business",
        "company_form",
        "turnover_k_eur",
        "employees",
        "operating_profit_k_eur",
        "facebook_url",
        "linkedin_url",
        "finder_url"
    ]

    try:
        with open(OUTPUT_CSV_DEDUP, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames_dedup, extrasaction='ignore')
            writer.writeheader()
            for idx, item in enumerate(dedup_list, 1):
                row = {"stt": idx}
                row.update(item)
                writer.writerow(row)
    except Exception as e:
        print(f"[!] Lỗi xuất CSV Dedup: {e}")

    # 4. Xuất CSV TẤT CẢ BẢN GHI (Gồm cả chi nhánh)
    fieldnames_all = [
        "stt",
        "name",
        "business_id",
        "website",
        "email",
        "phone",
        "address",
        "postal_code",
        "city",
        "province",
        "keyword",
        "tol_code",
        "tol_name",
        "line_of_business",
        "company_form",
        "turnover_k_eur",
        "employees",
        "operating_profit_k_eur",
        "facebook_url",
        "linkedin_url",
        "finder_url"
    ]

    try:
        with open(OUTPUT_CSV_ALL, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames_all, extrasaction='ignore')
            writer.writeheader()
            for idx, item in enumerate(all_raw_records, 1):
                row = {"stt": idx}
                row.update(item)
                writer.writerow(row)
    except Exception as e:
        print(f"[!] Lỗi xuất CSV All: {e}")

    # 5. Xuất Excel 2 sheet đẹp
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment

        wb = openpyxl.Workbook()
        
        # Sheet 1: Đã lọc trùng
        ws1 = wb.active
        ws1.title = "Đã lọc trùng (Duy nhất)"
        ws1.views.sheetView[0].showGridLines = True
        ws1.append(fieldnames_dedup)

        for idx, item in enumerate(dedup_list, 1):
            row = [idx] + [item.get(k, '') for k in fieldnames_dedup[1:]]
            ws1.append(row)

        # Sheet 2: Tất cả chi nhánh
        ws2 = wb.create_sheet(title="Tất cả chi nhánh")
        ws2.views.sheetView[0].showGridLines = True
        ws2.append(fieldnames_all)

        for idx, item in enumerate(all_raw_records, 1):
            row = [idx] + [item.get(k, '') for k in fieldnames_all[1:]]
            ws2.append(row)

        header_fill = PatternFill(start_color="003366", end_color="003366", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")

        for ws in [ws1, ws2]:
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
    except Exception as e:
        print(f"[!] Lỗi xuất Excel: {e}")

    # Thống kê
    total_dedup = len(dedup_list)
    total_www = sum(1 for x in dedup_list if x.get('website'))
    total_mail = sum(1 for x in dedup_list if x.get('email'))
    total_phone = sum(1 for x in dedup_list if x.get('phone'))

    print("\n" + "=" * 75)
    print("                 CẬP NHẬT KẾT QUẢ CÀO FINDER.FI")
    print("=" * 75)
    print(f"- Tổng số lượt xuất hiện (cả chi nhánh)     : {len(all_raw_records)}")
    print(f"- Tổng số DOANH NGHIỆP DUY NHẤT (ĐÃ LỌC TRÙNG): {total_dedup}")
    print(f"- Số doanh nghiệp có Website                 : {total_www} ({(total_www/total_dedup*100 if total_dedup else 0):.1f}%)")
    print(f"- Số doanh nghiệp có Email                   : {total_mail} ({(total_mail/total_dedup*100 if total_dedup else 0):.1f}%)")
    print(f"- Số doanh nghiệp có Số điện thoại           : {total_phone} ({(total_phone/total_dedup*100 if total_dedup else 0):.1f}%)")
    print(f"- File CSV kết quả chính (ĐÃ LỌC TRÙNG)      : {os.path.abspath(OUTPUT_CSV_DEDUP)}")
    print(f"- File Excel kết quả (.xlsx 2 sheet)         : {os.path.abspath(OUTPUT_XLSX)}")
    print("=" * 75)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cào dữ liệu tuyển dụng & cho thuê nhân sự từ finder.fi")
    parser.add_argument("--max-pages", type=int, default=None, help="Số trang tối đa mỗi từ khóa (mặc định cào hết)")
    parser.add_argument("--delay", type=float, default=0.4, help="Thời gian nghỉ giữa các trang (giây)")
    parser.add_argument("--no-deep-email", action="store_true", help="Tắt tính năng cào email từ website khi Finder thiếu")

    args = parser.parse_args()
    crawl_finder(
        keywords=DEFAULT_KEYWORDS,
        max_pages_per_kw=args.max_pages,
        delay=args.delay,
        deep_email=not args.no_deep_email
    )
