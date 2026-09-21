import sys
import io
import json
import time
import os
import re
import csv
import argparse
import random
from curl_cffi import requests
from bs4 import BeautifulSoup

# Đảm bảo in tiếng Việt trên console Windows không bị lỗi font
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

DEFAULT_URL = "https://www.proff.dk/branches%C3%B8g?q=Arbejdskrafts%20tjenester"
DEFAULT_CACHE = "crawlmail/cache_proff_arbejdskrafts.json"
DEFAULT_CSV = "proff_arbejdskrafts_tjenester.csv"

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

def extract_firma_links(html: str):
    """Trích xuất link chi tiết công ty theo companyId từ HTML"""
    links_by_id = {}
    try:
        soup = BeautifulSoup(html, 'html.parser')
        for a in soup.find_all('a', href=True):
            h = a['href']
            if h.startswith('/firma/'):
                parts = h.strip('/').split('/')
                if len(parts) >= 4:
                    company_id = parts[-1]
                    links_by_id[company_id] = f"https://www.proff.dk{h}"
    except Exception:
        pass
    return links_by_id

def crawl_proff(base_url=DEFAULT_URL, out_csv=DEFAULT_CSV, cache_file=DEFAULT_CACHE, max_pages=None, delay=2.5, timeout=60):
    os.makedirs(os.path.dirname(cache_file) if os.path.dirname(cache_file) else '.', exist_ok=True)
    
    # 1. Đọc dữ liệu đã cào trước đó nếu có (Resume capability)
    cached_data = {}
    visited_pages = set()
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                cached_data = saved.get('companies', {})
                visited_pages = set(saved.get('visited_pages', []))
                print(f"[*] Đã tải từ cache: {len(cached_data)} công ty, {len(visited_pages)} trang đã cào.")
        except Exception as e:
            print(f"[!] Không thể đọc cache: {e}")

    session = requests.Session()
    
    print(f"[*] Đang kết nối tới trang Proff.dk: {base_url}")
    print(f"[*] Cấu hình mạng VPN: Timeout={timeout}s, Delay={delay}s")
    # Lấy trang 1 để phân tích tổng số trang
    first_url = base_url if "page=" in base_url else f"{base_url}&page=1" if "?" in base_url else f"{base_url}?page=1"
    
    total_pages = 1
    total_hits = 0

    for attempt in range(4):
        try:
            r = session.get(first_url, impersonate="chrome124", timeout=timeout)
            if r.status_code == 200:
                next_data = extract_next_data(r.text)
                if next_data:
                    comp_store = next_data.get('props', {}).get('pageProps', {}).get('hydrationData', {}).get('searchStore', {}).get('companies', {})
                    total_hits = comp_store.get('hits', 0)
                    total_pages = comp_store.get('pages', 1)
                    print(f"[*] Tìm thấy tổng cộng: {total_hits} công ty ({total_pages} trang kết quả).")
                    break
                else:
                    print(f"[!] Dữ liệu chưa kịp tải xong từ máy chủ, thử lại sau 3s (lần {attempt+1}/4)...")
                    time.sleep(3)
            else:
                print(f"[!] Trang trả về mã HTTP {r.status_code}, thử lại sau 3s (lần {attempt+1}/4)...")
                time.sleep(3)
        except Exception as e:
            print(f"[!] Độ trễ VPN/Lỗi kết nối trang đầu (thử lại sau {3 + attempt*2}s - lần {attempt+1}/4): {e}")
            time.sleep(3 + attempt * 2)
    else:
        print("[!] Không thể lấy trang khởi đầu từ Proff.dk. Vui lòng kiểm tra kết nối mạng VPN.")
        return

    if max_pages and max_pages < total_pages:
        total_pages = max_pages
        print(f"[*] Giới hạn số trang cào theo yêu cầu: {total_pages} trang.")

    # 2. Vòng lặp duyệt từng trang
    clean_base = re.sub(r'[?&]page=\d+', '', base_url)
    sep = '&' if '?' in clean_base else '?'

    new_collected_count = 0
    start_time = time.time()

    for p in range(1, total_pages + 1):
        if p in visited_pages:
            continue

        page_url = f"{clean_base}{sep}page={p}"
        success = False

        for attempt in range(5):
            try:
                r = session.get(page_url, impersonate="chrome124", timeout=timeout)
                if r.status_code != 200:
                    print(f"[!] Trang {p} trả về mã HTTP {r.status_code}, thử lại sau 3s (lần {attempt+1}/5)...")
                    time.sleep(3)
                    continue

                next_data = extract_next_data(r.text)
                if not next_data:
                    print(f"[!] Trang {p} chưa có đủ cấu trúc dữ liệu JSON, thử lại sau 3s (lần {attempt+1}/5)...")
                    time.sleep(3)
                    continue

                links_map = extract_firma_links(r.text)
                comp_store = next_data.get('props', {}).get('pageProps', {}).get('hydrationData', {}).get('searchStore', {}).get('companies', {})
                items = comp_store.get('companies', [])

                if not items and p > 1:
                    # Hết kết quả
                    break

                page_phone_count = 0
                for c in items:
                    cvr = str(c.get('orgnr') or '').strip()
                    cid = str(c.get('companyId') or '').strip()
                    key = cvr or cid or str(c.get('name'))

                    # Thu thập số điện thoại
                    phones = []
                    for fld in ['phone', 'mobile', 'phone2', 'mobile2']:
                        val = c.get(fld)
                        if val and str(val).strip() and str(val).strip() not in phones:
                            phones.append(str(val).strip())
                    
                    phone_main = phones[0] if phones else ''
                    phone_all = "; ".join(phones)
                    if phone_main:
                        page_phone_count += 1

                    # Địa chỉ
                    visitor_addr = c.get('visitorAddress') or {}
                    location_info = c.get('location') or {}
                    contact_person = c.get('contactPerson') or {}

                    proff_url = links_map.get(cid, '')
                    if not proff_url and cid:
                        proff_url = f"https://www.proff.dk/branches%C3%B8g?q={cvr or cid}"

                    virk_url = f"https://datacvr.virk.dk/enhed/virksomhed/{cvr}" if cvr else ""

                    entry = {
                        "cvr": cvr,
                        "name": c.get('name') or '',
                        "legal_name": c.get('legalName') or '',
                        "phone": phone_main,
                        "phone_all": phone_all,
                        "email": c.get('email') or '',
                        "website": c.get('homePage') or '',
                        "address": visitor_addr.get('addressLine') or '',
                        "postal_code": visitor_addr.get('zipCode') or '',
                        "city": visitor_addr.get('postPlace') or '',
                        "region": location_info.get('countryPart') or '',
                        "municipality": location_info.get('municipality') or '',
                        "employees": c.get('employees') or '',
                        "contact_name": contact_person.get('name') or '',
                        "contact_role": contact_person.get('role') or '',
                        "revenue": c.get('revenue') or '',
                        "profit": c.get('profit') or '',
                        "company_id": cid,
                        "proff_url": proff_url,
                        "virk_url": virk_url
                    }

                    cached_data[key] = entry
                    new_collected_count += 1

                visited_pages.add(p)
                success = True
                print(f"[Trang {p:>3}/{total_pages}] Lấy +{len(items)} cty ({page_phone_count} có SĐT). Tổng tích lũy: {len(cached_data)} cty.")
                break

            except Exception as e:
                print(f"[!] Độ trễ VPN/Lỗi kết nối trang {p} (thử lại sau {3 + attempt*2}s - lần {attempt+1}/5): {e}")
                time.sleep(3 + attempt * 2)

        if not success:
            print(f"[!] Cảnh báo: Không tải được trang {p} sau các lần thử.")

        # Định kỳ lưu cache và file CSV mỗi 5 trang
        if p % 5 == 0 or p == total_pages:
            save_cache_and_csv(cached_data, visited_pages, cache_file, out_csv)

        # Delay ngẫu nhiên tránh nghẽn băng thông VPN và tránh bị chặn
        time.sleep(delay + random.uniform(0.5, 1.5))

    # 3. Lưu lần cuối
    save_cache_and_csv(cached_data, visited_pages, cache_file, out_csv)
    
    elapsed = time.time() - start_time
    total_companies = len(cached_data)
    total_phones = sum(1 for c in cached_data.values() if c.get('phone'))
    total_emails = sum(1 for c in cached_data.values() if c.get('email'))
    total_cvrs = sum(1 for c in cached_data.values() if c.get('cvr'))

    print("\n" + "=" * 60)
    print("                 HOÀN THÀNH CÀO PROFF.DK")
    print("=" * 60)
    print(f"- Tổng số công ty thu thập được: {total_companies}")
    print(f"- Số công ty có mã số CVR      : {total_cvrs} ({(total_cvrs/total_companies*100 if total_companies else 0):.1f}%)")
    print(f"- Số công ty có SĐT           : {total_phones} ({(total_phones/total_companies*100 if total_companies else 0):.1f}%)")
    print(f"- Số công ty có Email         : {total_emails} ({(total_emails/total_companies*100 if total_companies else 0):.1f}%)")
    print(f"- Thời gian thực hiện          : {elapsed:.1f} giây")
    print(f"- File CSV xuất ra            : {os.path.abspath(out_csv)}")
    print("=" * 60)

def save_cache_and_csv(cached_data, visited_pages, cache_file, out_csv):
    """Lưu cache JSON và xuất file CSV định dạng chuẩn Excel UTF-8"""
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump({
                "visited_pages": list(visited_pages),
                "companies": cached_data
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[!] Lỗi lưu cache JSON: {e}")

    try:
        fieldnames = [
            "cvr",
            "name",
            "legal_name",
            "phone",
            "phone_all",
            "email",
            "website",
            "address",
            "postal_code",
            "city",
            "region",
            "municipality",
            "employees",
            "contact_name",
            "contact_role",
            "revenue",
            "profit",
            "proff_url",
            "virk_url"
        ]

        with open(out_csv, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            for comp in cached_data.values():
                writer.writerow(comp)
    except Exception as e:
        print(f"[!] Lỗi xuất file CSV: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cào thông tin doanh nghiệp (CVR, SĐT, Email...) từ proff.dk")
    parser.add_argument("--url", default=DEFAULT_URL, help="URL tìm kiếm ngành nghề từ proff.dk")
    parser.add_argument("--out-csv", default=DEFAULT_CSV, help="Tên file CSV kết quả")
    parser.add_argument("--cache", default=DEFAULT_CACHE, help="Đường dẫn file cache JSON")
    parser.add_argument("--max-pages", type=int, default=None, help="Số trang tối đa cần cào (mặc định cào hết)")
    parser.add_argument("--delay", type=float, default=2.5, help="Thời gian delay giữa các trang (giây, mặc định 2.5s phù hợp mạng VPN)")
    parser.add_argument("--timeout", type=int, default=60, help="Thời gian timeout tải trang (giây, mặc định 60s phù hợp mạng VPN)")

    args = parser.parse_args()
    crawl_proff(
        base_url=args.url,
        out_csv=args.out_csv,
        cache_file=args.cache,
        max_pages=args.max_pages,
        delay=args.delay,
        timeout=args.timeout
    )
