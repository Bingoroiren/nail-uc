# -*- coding: utf-8 -*-
"""
Hệ thống Làm giàu Dữ liệu Tuyển dụng & Môi giới Lao động Na Uy:
NOPROFF.csv -> NOPODATA.csv

Quy trình:
1. Nhận đầu vào: NOPROFF.csv (4.791 công ty ngành Arbeidskrafttjenester từ Proff.no).
2. Tra cứu Open API Cục Đăng ký Doanh nghiệp Na Uy (Brønnøysundregistrene - Brreg):
   - Tra cứu Enhet: https://data.brreg.no/enhetsregisteret/api/enheter/{orgnr}
   - Fallback Underenhet: https://data.brreg.no/enhetsregisteret/api/underenheter/{orgnr}
   - Trích xuất: Website chính thức (hjemmeside), Email đăng ký (epostadresse),
     SĐT (telefon/mobil), Mã ngành NACE chuẩn, Số nhân viên, Trạng thái (Phá sản/Giải thể).
3. Cào Website doanh nghiệp để lấy Email B2B chất lượng cao:
   - Quét trang chủ và các trang con liên hệ (/kontakt, /contact, /om-os, /jobb, /om-oss).
   - Loại bỏ triệt để ký tự rác (%20, mailto:).
   - Lọc bỏ email rác hệ thống (sentry, wixpress, noreply, gdpr, privacy, terms, example.com...).
   - Chấm điểm chọn 1 Email B2B tốt nhất cho môi giới lao động / tuyển dụng
     (post@, kontakt@, info@, rekruttering@, hr@, job@, booking@...).
4. Lưu file động tức thời:
   - Ghi trực tiếp liên tục vào NOPODATA.csv và Cache JSON.
   - Hỗ trợ Resume 100% khi tạm dừng hoặc chạy tiếp trên máy khác.
"""

import sys
import io
import json
import time
import os
import re
import csv
import html
import asyncio
import urllib.parse
from urllib.parse import urlparse
from pathlib import Path
from bs4 import BeautifulSoup

try:
    from curl_cffi.requests import AsyncSession
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False
    import aiohttp

# Đảm bảo in tiếng Việt trên console Windows không bị lỗi font
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent

INPUT_CSV = str(BASE_DIR / "NOPROFF.csv")
OUTPUT_CSV = str(BASE_DIR / "NOPODATA.csv")
CACHE_FILE = str(SCRIPT_DIR / "cache_enrich_nopodata.json")

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,10}\b')

# Tên miền rác, hệ thống hoặc mẫu demo
JUNK_EMAIL_DOMAINS = {
    'facebook.com', 'twitter.com', 'instagram.com', 'linkedin.com', 'youtube.com',
    'wix.com', 'wixsite.com', 'wordpress.com', 'squarespace.com', 'weebly.com',
    'godaddy.com', 'example.com', 'domain.com', 'placeholder.com', 'wixpress.com',
    'sentry.io', 'sentry.wixpress.com', 'sentry-next.wixpress.com', 'schema.org',
    'trustpilot.com', 'trustpilot.no', 'google.com', 'google.no'
}

SYSTEM_USERNAMES = {
    'noreply', 'no-reply', 'donotreply', 'privacy', 'terms', 'cookies', 'gdpr',
    'abuse', 'security', 'webmaster', 'sentry', 'admin', 'mailer-daemon',
    'test', 'user', 'example', 'postmaster'
}

B2B_STAFFING_USERNAMES = [
    'post', 'kontakt', 'info', 'rekruttering', 'jobb', 'job', 'karriere',
    'hr', 'bemanning', 'vikar', 'booking', 'administrasjon', 'kontor',
    'office', 'salg', 'sales', 'support', 'firmapost'
]

def clean_email_string(email_str):
    """Làm sạch email, loại bỏ %20 và ký tự thừa."""
    if not email_str:
        return ""
    em = urllib.parse.unquote(str(email_str)).replace('%20', '').strip().lower().rstrip('.,;:')
    if any(em.endswith(ext) for ext in ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.pdf', '.css', '.js')):
        return ""
    if '@' not in em or len(em) < 6:
        return ""
    u, d = em.split('@', 1)
    if d in JUNK_EMAIL_DOMAINS or u in SYSTEM_USERNAMES:
        return ""
    return em

def score_email_b2b(email, comp_domain=""):
    """Chấm điểm email để chọn 1 email B2B tốt nhất cho công ty nhân sự/tuyển dụng Na Uy."""
    clean_em = clean_email_string(email)
    if not clean_em:
        return 0
    u, d = clean_em.split('@', 1)

    score = 10
    # Khớp tên miền công ty (+25 điểm)
    if comp_domain and (d == comp_domain or comp_domain.endswith('.' + d) or d.endswith('.' + comp_domain)):
        score += 25
    # Tiền tố tuyển dụng / nhân sự B2B Na Uy (+20 điểm)
    if any(u == b or u.startswith(b + '.') or u.startswith(b + '-') for b in B2B_STAFFING_USERNAMES):
        score += 20
    # Email dạng post@, kontakt@, info@ tại tên miền công ty là tối ưu nhất Na Uy
    if u in ['post', 'kontakt', 'info', 'firmapost'] and comp_domain and (d == comp_domain or comp_domain.endswith('.' + d)):
        score += 15
    # Trừ điểm email miễn phí
    if d in ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'live.no', 'online.no']:
        score -= 8

    return score

def clean_phone_no(phone_str):
    """Chuẩn hóa số điện thoại Na Uy (+47, 8 số, có dấu nháy đơn cho Excel)."""
    if not phone_str:
        return ""
    p = str(phone_str).strip()
    p = re.sub(r'[\ue000-\uf8ff]', '', p).strip()
    digits = re.sub(r'[^\d]', '', p)
    if not digits:
        return ""
    if digits.startswith("0047"):
        digits = digits[4:]
    elif digits.startswith("47") and len(digits) >= 10:
        digits = digits[2:]

    if len(digits) == 8:
        return f"'+47{digits}"
    return f"'+47 {p}" if not p.startswith("+") and not p.startswith("'") else f"'{p}"

def normalize_website_url(url_str):
    """Chuẩn hóa đường dẫn website."""
    if not url_str:
        return ""
    u = str(url_str).replace('%20', '').strip()
    if not u or u.lower() in ('none', 'null', '-'):
        return ""
    if not u.startswith("http://") and not u.startswith("https://"):
        u = "https://" + u
    return u.rstrip('/')

async def fetch_html_content(session, url, timeout=8):
    """Tải nội dung HTML nhanh."""
    if not url or not url.startswith('http'):
        return ""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "no,nb,nn,en-US;q=0.9,en;q=0.8"
    }
    try:
        if HAS_CURL_CFFI:
            resp = await session.get(url, headers=headers, impersonate="chrome124", timeout=timeout, verify=False)
            if resp.status_code == 200:
                return resp.text
        else:
            async with session.get(url, headers=headers, timeout=timeout, ssl=False) as resp:
                if resp.status == 200:
                    return await resp.text()
    except Exception:
        pass
    return ""

def extract_emails_from_html(html_str):
    """Trích xuất email từ mã nguồn HTML."""
    if not html_str:
        return set()
    found = set()
    unescaped = html.unescape(html_str)

    # 1. mailto: links (loại bỏ %20)
    for mailto in re.findall(r'mailto:([^\s"\'<>]+)', unescaped, re.IGNORECASE):
        cleaned_m = mailto.split('?')[0]
        em = clean_email_string(cleaned_m)
        if em:
            found.add(em)

    # 2. Plain text regex
    for match in EMAIL_REGEX.findall(unescaped):
        em = clean_email_string(match)
        if em:
            found.add(em)

    return found

async def scrape_website_b2b_email(session, website_url):
    """Quét trang chủ và trang liên hệ của website công ty để tìm 1 email B2B tốt nhất."""
    clean_web = normalize_website_url(website_url)
    if not clean_web:
        return ""
    try:
        comp_domain = urlparse(clean_web).netloc.lower().replace('www.', '')
    except Exception:
        comp_domain = ""

    raw_emails = set()

    # 1. Quét trang chủ
    home_html = await fetch_html_content(session, clean_web, timeout=7)
    if home_html:
        raw_emails.update(extract_emails_from_html(home_html))

        # Quét tìm tối đa 2 trang con liên hệ
        try:
            soup = BeautifulSoup(home_html, 'html.parser')
            sub_links = []
            for a in soup.find_all('a', href=True):
                h = a['href'].strip()
                t = a.get_text().strip().lower()
                hl = h.lower()
                if any(k in hl or k in t for k in ['kontakt', 'contact', 'om-oss', 'om', 'jobb', 'rekruttering', 'bemanning']):
                    full = urllib.parse.urljoin(clean_web, h)
                    if full.startswith(clean_web) and full not in sub_links and full != clean_web:
                        sub_links.append(full)
            for s_url in sub_links[:2]:
                s_html = await fetch_html_content(session, s_url, timeout=6)
                if s_html:
                    raw_emails.update(extract_emails_from_html(s_html))
        except Exception:
            pass

    if not raw_emails:
        return ""

    scored = []
    for em in raw_emails:
        sc = score_email_b2b(em, comp_domain)
        if sc > 0:
            scored.append((sc, clean_email_string(em)))

    if scored:
        scored.sort(key=lambda x: (x[0], -len(x[1])), reverse=True)
        return scored[0][1]
    return ""

async def query_brreg_api(session, orgnr):
    """Tra cứu thông tin chính thức từ API Cục Đăng ký Doanh nghiệp Na Uy (Brreg)."""
    clean_org = str(orgnr).replace("'", "").strip()
    if not clean_org or len(clean_org) < 8:
        return {}

    res_data = {}
    url_enhet = f"https://data.brreg.no/enhetsregisteret/api/enheter/{clean_org}"
    url_under = f"https://data.brreg.no/enhetsregisteret/api/underenheter/{clean_org}"

    headers = {"Accept": "application/json"}

    try:
        if HAS_CURL_CFFI:
            resp = await session.get(url_enhet, headers=headers, timeout=6)
            if resp.status_code == 200:
                res_data = resp.json()
            elif resp.status_code == 404:
                resp2 = await session.get(url_under, headers=headers, timeout=6)
                if resp2.status_code == 200:
                    res_data = resp2.json()
        else:
            async with session.get(url_enhet, headers=headers, timeout=6) as resp:
                if resp.status == 200:
                    res_data = await resp.json()
                elif resp.status == 404:
                    async with session.get(url_under, headers=headers, timeout=6) as resp2:
                        if resp2.status == 200:
                            res_data = await resp2.json()
    except Exception:
        pass

    return res_data

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_cache(cache):
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        tmp = CACHE_FILE + ".tmp"
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(tmp):
            os.replace(tmp, CACHE_FILE)
    except Exception:
        pass

def save_csv_dynamically(rows, fieldnames, target_path):
    tmp = target_path + ".tmp"
    try:
        with open(tmp, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            f.flush()
            os.fsync(f.fileno())
        for attempt in range(3):
            try:
                if os.path.exists(tmp):
                    os.replace(tmp, target_path)
                break
            except PermissionError:
                time.sleep(0.4)
    except Exception as e:
        print(f"[-] Lỗi lưu file CSV: {e}")

async def process_company(row, session, cache):
    """Xử lý làm giàu cho 1 công ty."""
    orgnr_raw = row.get("orgnr", "").strip()
    clean_org = orgnr_raw.replace("'", "").strip()
    comp_name = row.get("name", "").strip()
    key = clean_org or comp_name

    # 1. Kiểm tra cache
    cached = cache.get(key)
    if cached:
        row["email"] = cached.get("email") or row.get("email", "")
        row["website"] = cached.get("website") or row.get("website", "")
        row["phone"] = cached.get("phone") or row.get("phone", "")
        row["nace_code"] = cached.get("nace_code", "")
        row["nace_name"] = cached.get("nace_name", "")
        row["legal_form"] = cached.get("legal_form", "")
        row["status_brreg"] = cached.get("status_brreg", "")
        row["Check gui"] = "OK" if row.get("email") else ""
        return row, False

    # 2. Gọi Brreg API
    brreg = await query_brreg_api(session, clean_org)

    brreg_email = clean_email_string(brreg.get("epostadresse", ""))
    brreg_web = normalize_website_url(brreg.get("hjemmeside", ""))
    brreg_phone = brreg.get("telefon") or brreg.get("mobil") or ""
    nace_info = brreg.get("naeringskode1") or {}
    nace_code = nace_info.get("kode", "")
    nace_name = nace_info.get("beskrivelse", "")
    org_form = (brreg.get("organisasjonsform") or {}).get("kode", "")
    
    # Kiểm tra tình trạng phá sản / giải thể
    is_konkurs = brreg.get("konkurs", False)
    is_avvikling = brreg.get("underAvvikling", False)
    status_brreg = "Konkurs" if is_konkurs else ("Avvikling" if is_avvikling else "Aktiv")

    # Xác định Website tốt nhất (từ Proff hoặc Brreg)
    current_web = normalize_website_url(row.get("website", ""))
    best_web = current_web or brreg_web

    # Xác định Số điện thoại
    current_phone = row.get("phone", "").strip()
    if brreg_phone and not current_phone:
        current_phone = clean_phone_no(brreg_phone)

    # 3. Cào Website để tìm Email B2B tối ưu nhất
    web_email = ""
    if best_web:
        web_email = await scrape_website_b2b_email(session, best_web)

    # Chọn email cuối cùng: Ưu tiên email B2B cào từ website > email đăng ký Brreg > email cũ Proff
    final_email = web_email or brreg_email or clean_email_string(row.get("email", ""))

    row["email"] = final_email
    row["website"] = best_web
    row["phone"] = current_phone
    row["nace_code"] = nace_code
    row["nace_name"] = nace_name
    row["legal_form"] = org_form
    row["status_brreg"] = status_brreg
    row["Check gui"] = "OK" if final_email else ""

    # Lưu cache
    cache[key] = {
        "email": final_email,
        "website": best_web,
        "phone": current_phone,
        "nace_code": nace_code,
        "nace_name": nace_name,
        "legal_form": org_form,
        "status_brreg": status_brreg
    }

    return row, True

async def run_enrichment():
    if not os.path.exists(INPUT_CSV):
        print(f"[ERROR] Không tìm thấy file đầu vào: {INPUT_CSV}!")
        return

    # 1. Khởi tạo file kết quả NOPODATA.csv từ NOPROFF.csv nếu chưa có
    if not os.path.exists(OUTPUT_CSV):
        print(f"[*] Khởi tạo file kết quả: {OUTPUT_CSV} từ {INPUT_CSV} ...")
        try:
            import shutil
            shutil.copy2(INPUT_CSV, OUTPUT_CSV)
        except Exception as e:
            print(f"[-] Cảnh báo khởi tạo file: {e}")

    # 2. Đọc file kết quả hiện tại
    with open(OUTPUT_CSV, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    # Bổ sung các cột làm giàu mới nếu chưa có
    enrich_cols = ["Check gui", "nace_code", "nace_name", "legal_form", "status_brreg"]
    for col in enrich_cols:
        if col not in fieldnames:
            fieldnames.append(col)

    cache = load_cache()
    total_rows = len(rows)

    print("=" * 72)
    print("    HỆ THỐNG LÀM GIÀU DỮ LIỆU CÔNG TY NA UY: NOPROFF -> NOPODATA")
    print(f"    Tập tin gốc:    {INPUT_CSV}")
    print(f"    Tập tin kết quả: {OUTPUT_CSV}")
    print(f"    Tổng số công ty: {total_rows:,}")
    print(f"    Bản ghi trong Cache: {len(cache):,}")
    print("=" * 72)

    # Tìm các dòng chưa có email hoặc chưa được làm giàu
    need_process = []
    for idx, r in enumerate(rows):
        key = r.get("orgnr", "").replace("'", "").strip() or r.get("name", "").strip()
        if not r.get("email", "").strip() or key not in cache:
            need_process.append(idx)

    print(f"[*] Số công ty cần làm giàu / bổ sung: {len(need_process):,}")

    if not need_process:
        print("[+] Tuyệt vời! Tất cả các dòng đã hoàn tất làm giàu dữ liệu.")
        return

    # Khởi tạo session
    if HAS_CURL_CFFI:
        session = AsyncSession(impersonate="chrome124")
    else:
        session = aiohttp.ClientSession()

    processed = 0
    new_emails = 0
    batch_size = 10
    start_time = time.time()

    try:
        # Xử lý theo lô để tối ưu tốc độ và an toàn kết nối
        for i in range(0, len(need_process), batch_size):
            batch_indices = need_process[i:i + batch_size]
            tasks = [process_company(rows[idx], session, cache) for idx in batch_indices]
            results = await asyncio.gather(*tasks)

            for updated_row, is_new in results:
                processed += 1
                if updated_row.get("email"):
                    new_emails += 1

            # In tiến độ
            curr_row = rows[batch_indices[-1]]
            print(f"[{processed:>4}/{len(need_process):,}] Đã xử lý: {curr_row['name'][:30]:<30} | Mail: {curr_row.get('email', '')[:25]:<25} | Web: {curr_row.get('website', '')[:25]}")

            # Lưu cache & CSV động liên tục mỗi lô
            save_cache(cache)
            save_csv_dynamically(rows, fieldnames, OUTPUT_CSV)

            await asyncio.sleep(0.3)

    finally:
        if HAS_CURL_CFFI:
            await session.close()
        else:
            await session.close()

    # Thống kê lần cuối
    total_emails = sum(1 for r in rows if r.get("email", "").strip())
    total_webs = sum(1 for r in rows if r.get("website", "").strip())
    total_phones = sum(1 for r in rows if r.get("phone", "").strip())

    print("\n" + "=" * 72)
    print("          HOÀN TẤT LÀM GIÀU DỮ LIỆU CHO NOPODATA.CSV!")
    print("=" * 72)
    print(f"- Tổng số công ty          : {total_rows:,}")
    print(f"- Số công ty có Email      : {total_emails:,} ({(total_emails/total_rows*100):.1f}%)")
    print(f"- Số công ty có Website    : {total_webs:,} ({(total_webs/total_rows*100):.1f}%)")
    print(f"- Số công ty có SĐT        : {total_phones:,} ({(total_phones/total_rows*100):.1f}%)")
    print(f"- Thời gian thực hiện      : {time.time() - start_time:.1f} giây")
    print(f"- File kết quả đã lưu tại  : {OUTPUT_CSV}")
    print("=" * 72)

if __name__ == "__main__":
    asyncio.run(run_enrichment())
