# -*- coding: utf-8 -*-
"""
Hệ thống cào toàn bộ danh sách công ty từ Proff.no (Na Uy)
Ngành: Arbeidskrafttjenester (Dịch vụ lao động, Cung ứng nhân lực, Tuyển dụng)
URL: https://www.proff.no/bransjes%C3%B8k?q=Arbeidskrafttjenester
Tổng số: ~5.958 công ty (239 trang kết quả)

Đặc điểm kỹ thuật:
- Trích xuất dữ liệu JSON hydration trực tiếp từ Next.js tag __NEXT_DATA__
- Tốc độ cao với curl_cffi giả lập Chrome 124
- Lưu trữ động liên tục vào Cache JSON và CSV (UTF-8 with BOM chuẩn Excel)
- Hỗ trợ Resume tự động (bấm Ctrl+C dừng rồi chạy tiếp không mất dữ liệu)
- Đầy đủ thông tin: Orgnr, Tên công ty, SĐT, Email, Website, Địa chỉ, Thành phố, Hạt, Nhân viên, Doanh thu, Lợi nhuận, Link Proff, Link Brønnøysundregistrene (Brreg).
"""

import sys
import io
import json
import time
import os
import re
import csv
import argparse
import random
from pathlib import Path
from bs4 import BeautifulSoup

try:
    from curl_cffi import requests
except ImportError:
    import requests

# Đảm bảo in tiếng Việt trên console Windows không bị lỗi font
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent

DEFAULT_URL = "https://www.proff.no/bransjes%C3%B8k?q=Arbeidskrafttjenester"
DEFAULT_CACHE = str(SCRIPT_DIR / "cache_proff_no_arbeidskrafttjenester.json")
DEFAULT_CSV = str(BASE_DIR / "NOPROFF.csv")

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

def extract_selskap_links(html: str):
    """Trích xuất link chi tiết công ty theo companyId từ HTML"""
    links_by_id = {}
    try:
        soup = BeautifulSoup(html, 'html.parser')
        for a in soup.find_all('a', href=True):
            h = a['href']
            if '/selskap/' in h:
                parts = h.strip('/').split('/')
                if parts:
                    company_id = parts[-1]
                    links_by_id[company_id] = f"https://www.proff.no{h}" if h.startswith('/') else h
    except Exception:
        pass
    return links_by_id

def clean_phone_no(phone_str):
    """Làm sạch và chuẩn hóa số điện thoại Na Uy"""
    if not phone_str:
        return ""
    p = str(phone_str).strip()
    # Loại bỏ icon hoặc ký tự lạ
    p = re.sub(r'[\ue000-\uf8ff]', '', p).strip()
    return f"'{p}" if not p.startswith("'") else p

def crawl_proff_no(base_url=DEFAULT_URL, out_csv=DEFAULT_CSV, cache_file=DEFAULT_CACHE, max_pages=None, delay=1.0, timeout=45):
    os.makedirs(os.path.dirname(os.path.abspath(cache_file)), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(out_csv)), exist_ok=True)

    # 1. Đọc dữ liệu đã cào trước đó nếu có (Resume)
    cached_data = {}
    visited_pages = set()
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                cached_data = saved.get('companies', {})
                visited_pages = set(saved.get('visited_pages', []))
                print(f"[*] Đã tải từ cache: {len(cached_data):,} công ty, {len(visited_pages)} trang đã cào thành công.")
        except Exception as e:
            print(f"[!] Không thể đọc cache: {e}")

    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "no,nb,nn,en-US,en;q=0.9",
        "Referer": "https://www.proff.no/",
    }

    print("=" * 72)
    print("       CÀO DỮ LIỆU CÔNG TY TỪ PROFF.NO (NA UY - NORWAY)")
    print(f"       Từ khóa ngành: Arbeidskrafttjenester (Nhân lực & Lao động)")
    print(f"       File kết quả CSV: {out_csv}")
    print(f"       File lưu Cache:   {cache_file}")
    print("=" * 72)

    # Lấy trang 1 để kiểm tra tổng số lượng công ty & tổng số trang
    clean_base = re.sub(r'[?&]page=\d+', '', base_url)
    sep = '&' if '?' in clean_base else '?'
    first_url = f"{clean_base}{sep}page=1"

    total_pages = 239
    total_hits = 5958

    print(f"[*] Đang kết nối tới trang đầu: {first_url} ...")
    for attempt in range(5):
        try:
            r = session.get(first_url, headers=headers, impersonate="chrome124", timeout=timeout)
            if r.status_code == 200:
                next_data = extract_next_data(r.text)
                if next_data:
                    comp_store = next_data.get('props', {}).get('pageProps', {}).get('hydrationData', {}).get('searchStore', {}).get('companies', {})
                    hits = comp_store.get('hits')
                    pages = comp_store.get('pages')
                    if hits:
                        total_hits = hits
                    if pages:
                        total_pages = pages
                    print(f"[+] Tìm thấy tổng cộng: {total_hits:,} công ty ({total_pages:,} trang kết quả).")
                    break
                else:
                    print(f"[!] Trang chưa có đủ cấu trúc JSON, thử lại sau 2s (lần {attempt+1}/5)...")
                    time.sleep(2)
            else:
                print(f"[!] Trang trả về mã HTTP {r.status_code}, thử lại sau 2s (lần {attempt+1}/5)...")
                time.sleep(2)
        except Exception as e:
            print(f"[!] Lỗi kết nối trang đầu (thử lại sau {2 + attempt*2}s): {e}")
            time.sleep(2 + attempt * 2)

    if max_pages and max_pages < total_pages:
        total_pages = max_pages
        print(f"[*] Giới hạn số trang cào theo yêu cầu: {total_pages} trang.")

    # 2. Vòng lặp duyệt từng trang
    start_time = time.time()
    new_collected_count = 0

    for p in range(1, total_pages + 1):
        if p in visited_pages:
            continue

        page_url = f"{clean_base}{sep}page={p}"
        success = False

        for attempt in range(5):
            try:
                r = session.get(page_url, headers=headers, impersonate="chrome124", timeout=timeout)
                if r.status_code != 200:
                    print(f"[!] Trang {p} trả về mã HTTP {r.status_code}, thử lại sau 2s (lần {attempt+1}/5)...")
                    time.sleep(2)
                    continue

                next_data = extract_next_data(r.text)
                if not next_data:
                    print(f"[!] Trang {p} chưa có cấu trúc JSON, thử lại sau 2s (lần {attempt+1}/5)...")
                    time.sleep(2)
                    continue

                links_map = extract_selskap_links(r.text)
                comp_store = next_data.get('props', {}).get('pageProps', {}).get('hydrationData', {}).get('searchStore', {}).get('companies', {})
                items = comp_store.get('companies', [])

                if not items and p > 1:
                    print(f"[*] Trang {p} không còn dữ liệu kết quả.")
                    break

                page_phone_count = 0
                page_email_count = 0

                for c in items:
                    orgnr = str(c.get('orgnr') or '').strip()
                    cid = str(c.get('companyId') or '').strip()
                    name = str(c.get('name') or '').strip()
                    key = orgnr or cid or name

                    # Thu thập các số điện thoại
                    phones = []
                    for fld in ['phone', 'phone2', 'mobile', 'mobile2']:
                        val = c.get(fld)
                        if val and str(val).strip() and str(val).strip() not in phones:
                            phones.append(str(val).strip())

                    phone_main = clean_phone_no(phones[0]) if phones else ''
                    phone_all = "; ".join([clean_phone_no(x) for x in phones])
                    if phone_main:
                        page_phone_count += 1

                    email = str(c.get('email') or '').strip()
                    if email:
                        page_email_count += 1

                    # Địa chỉ khách (visitorAddress) hoặc bưu điện (postalAddress)
                    v_addr = c.get('visitorAddress') or {}
                    p_addr = c.get('postalAddress') or {}
                    addr_line = v_addr.get('addressLine') or p_addr.get('addressLine') or ''
                    zip_code = v_addr.get('zipCode') or p_addr.get('zipCode') or ''
                    post_place = v_addr.get('postPlace') or p_addr.get('postPlace') or ''

                    location_info = c.get('location') or {}
                    contact_person = c.get('contactPerson') or {}

                    proff_url = links_map.get(cid, '')
                    if not proff_url and cid:
                        proff_url = f"https://www.proff.no/bransjes%C3%B8k?q={orgnr or cid}"

                    brreg_url = f"https://virksomhet.brreg.no/nb/oppslag/enheter/{orgnr}" if orgnr else ""

                    entry = {
                        "orgnr": f"'{orgnr}" if orgnr else "",
                        "name": name,
                        "legal_name": str(c.get('legalName') or '').strip(),
                        "phone": phone_main,
                        "phone_all": phone_all,
                        "email": email,
                        "website": str(c.get('homePage') or '').strip(),
                        "address": addr_line,
                        "postal_code": str(zip_code).strip(),
                        "city": post_place,
                        "municipality": str(location_info.get('municipality') or '').strip(),
                        "county": str(location_info.get('county') or '').strip(),
                        "region": str(location_info.get('countryPart') or '').strip(),
                        "employees": str(c.get('employees') or '').strip(),
                        "contact_name": str(contact_person.get('name') or '').strip(),
                        "contact_role": str(contact_person.get('role') or '').strip(),
                        "revenue": str(c.get('revenue') or '').strip(),
                        "profit": str(c.get('profit') or '').strip(),
                        "currency": str(c.get('currency') or 'NOK').strip(),
                        "status": str(c.get('status') or '').strip(),
                        "company_id": cid,
                        "proff_url": proff_url,
                        "brreg_url": brreg_url
                    }

                    cached_data[key] = entry
                    new_collected_count += 1

                visited_pages.add(p)
                success = True
                print(f"[Trang {p:>3}/{total_pages}] +{len(items)} cty ({page_phone_count} SĐT, {page_email_count} Email). Tổng: {len(cached_data):,} cty.")
                break

            except Exception as e:
                print(f"[!] Lỗi kết nối trang {p} (thử lại sau {2 + attempt*2}s): {e}")
                time.sleep(2 + attempt * 2)

        if not success:
            print(f"[!] Cảnh báo: Không thể tải xong trang {p} sau các lần thử lại.")

        # Lưu tự động mỗi 3 trang hoặc trang cuối
        if p % 3 == 0 or p == total_pages:
            save_cache_and_csv(cached_data, visited_pages, cache_file, out_csv)

        # Nghỉ nhẹ giữa các request để bảo vệ kết nối
        time.sleep(delay + random.uniform(0.2, 0.6))

    # 3. Lưu lần cuối
    save_cache_and_csv(cached_data, visited_pages, cache_file, out_csv)

    elapsed = time.time() - start_time
    total_companies = len(cached_data)
    total_phones = sum(1 for c in cached_data.values() if c.get('phone'))
    total_emails = sum(1 for c in cached_data.values() if c.get('email'))
    total_websites = sum(1 for c in cached_data.values() if c.get('website'))
    total_orgnrs = sum(1 for c in cached_data.values() if c.get('orgnr'))

    print("\n" + "=" * 72)
    print("                 HOÀN THÀNH CÀO PROFF.NO")
    print("=" * 72)
    print(f"- Tổng số công ty đã lưu       : {total_companies:,}")
    print(f"- Số công ty có Mã Orgnr       : {total_orgnrs:,} ({(total_orgnrs/total_companies*100 if total_companies else 0):.1f}%)")
    print(f"- Số công ty có Số điện thoại  : {total_phones:,} ({(total_phones/total_companies*100 if total_companies else 0):.1f}%)")
    print(f"- Số công ty có Email          : {total_emails:,} ({(total_emails/total_companies*100 if total_companies else 0):.1f}%)")
    print(f"- Số công ty có Website        : {total_websites:,} ({(total_websites/total_companies*100 if total_websites else 0):.1f}%)")
    print(f"- Tổng thời gian cào           : {elapsed:.1f} giây")
    print(f"- Tập tin kết quả CSV          : {os.path.abspath(out_csv)}")
    print("=" * 72)

def save_cache_and_csv(cached_data, visited_pages, cache_file, out_csv):
    """Lưu cache JSON và ghi an toàn ra file CSV định dạng chuẩn UTF-8-BOM cho Excel."""
    # 1. Lưu Cache JSON
    try:
        temp_cache = cache_file + ".tmp"
        with open(temp_cache, 'w', encoding='utf-8') as f:
            json.dump({
                "visited_pages": list(visited_pages),
                "companies": cached_data
            }, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(temp_cache):
            os.replace(temp_cache, cache_file)
    except Exception as e:
        print(f"[!] Lỗi lưu cache JSON: {e}")

    # 2. Lưu CSV
    try:
        fieldnames = [
            "orgnr",
            "name",
            "legal_name",
            "phone",
            "phone_all",
            "email",
            "website",
            "address",
            "postal_code",
            "city",
            "municipality",
            "county",
            "region",
            "employees",
            "contact_name",
            "contact_role",
            "revenue",
            "profit",
            "currency",
            "status",
            "company_id",
            "proff_url",
            "brreg_url"
        ]

        temp_csv = out_csv + ".tmp"
        with open(temp_csv, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in cached_data.values():
                writer.writerow(row)
            f.flush()
            os.fsync(f.fileno())

        for attempt in range(3):
            try:
                if os.path.exists(temp_csv):
                    os.replace(temp_csv, out_csv)
                break
            except PermissionError:
                time.sleep(0.5)
    except Exception as e:
        print(f"[!] Lỗi lưu file CSV: {e}")

def main():
    parser = argparse.ArgumentParser(description="Cào danh sách công ty từ Proff.no")
    parser.add_argument("--url", "-u", default=DEFAULT_URL, help="URL tìm kiếm Proff.no")
    parser.add_argument("--output", "-o", default=DEFAULT_CSV, help="Đường dẫn file CSV kết quả")
    parser.add_argument("--cache", "-c", default=DEFAULT_CACHE, help="Đường dẫn file cache JSON")
    parser.add_argument("--max-pages", "-m", type=int, default=None, help="Giới hạn số trang cào (mặc định cào hết)")
    parser.add_argument("--delay", "-d", type=float, default=0.8, help="Thời gian nghỉ giữa các trang (giây)")
    args = parser.parse_args()

    crawl_proff_no(
        base_url=args.url,
        out_csv=args.output,
        cache_file=args.cache,
        max_pages=args.max_pages,
        delay=args.delay
    )

if __name__ == "__main__":
    main()
