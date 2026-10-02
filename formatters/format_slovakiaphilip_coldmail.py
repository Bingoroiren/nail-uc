# -*- coding: utf-8 -*-
"""
Script Chuẩn Hóa slovakiaphilip.csv Sang Mẫu Cold Mail Tiêu Chuẩn Workspace (20 Cột):
Header chuẩn 20 cột:
['No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ', 
 'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển', 
 'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply', 
 'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category']
"""

import sys
import os
import re
import csv
import json
import shutil
import urllib.parse
from pathlib import Path
from collections import defaultdict

# Đảm bảo UTF-8 cho Windows Console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = ROOT_DIR / "slovakiaphilip.csv"
BACKUP_CSV = ROOT_DIR / "slovakiaphilip_backup_raw.csv"
OUTPUT_COLDMAIL_CSV = ROOT_DIR / "slovakiaphilip_ColdMail.csv"

DMW_ORDERS = ROOT_DIR / "data" / "raw" / "dmw_approved_job_orders_slovakia.csv"
DMW_AGG = ROOT_DIR / "data" / "raw" / "dmw_slovakia_principals_aggregated.csv"
MAPS_CACHE = ROOT_DIR / "crawlmail" / "cache_enrich_maps_slovakiaphilip.json"

FIELDNAMES = [
    "No.",
    "Công ty",
    "Chức danh",
    "Người liên hệ",
    "SĐT",
    "Liên Hệ",
    "Email",
    "Liên Hệ mail",
    "Địa chỉ",
    "Lương",
    "Ngày đăng",
    "Hạn tuyển",
    "Check gửi",
    "Last Subject",
    "Last Body HTML",
    "Trạng thái Reply",
    "Lần Follow-up",
    "Ngày Follow-up gần nhất",
    "Mailbox đã dùng",
    "Category"
]

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Z|a-z]{2,10}\b')

JUNK_EMAIL_DOMAINS = {
    'facebook.com', 'twitter.com', 'instagram.com', 'linkedin.com', 'youtube.com',
    'wix.com', 'wixsite.com', 'wordpress.com', 'squarespace.com', 'weebly.com',
    'godaddy.com', 'example.com', 'domain.com', 'placeholder.com', 'wixpress.com',
    'sentry.io', 'sentry-next.wixpress.com', 'sentry.wixpress.com', 'schema.org', 'trustpilot.com', 'google.com',
    'example.com', 'example.org', 'example.net', 'domain.com', 'yourdomain.com', 'yourcompany.com',
    'your-domain.com', 'your-site.com', 'mydomain.com', 'mycompany.com', 'company.com', 'website.com',
    'site.com', 'placeholder.com', 'sample.com', 'demo.com', 'templatemonster.com', 'themeforest.net'
}

SYSTEM_USERNAMES = {
    'noreply', 'no-reply', 'donotreply', 'privacy', 'terms', 'cookies', 'gdpr',
    'abuse', 'security', 'webmaster', 'sentry', 'mailer-daemon', 'test', 'example',
    'hostmaster', 'postmaster', 'root'
}

TEMPLATE_USERNAMES = {
    'youremail', 'your-email', 'your_email', 'your.email',
    'yourname', 'your-name', 'your_name', 'your.name',
    'yourcompany', 'myemail', 'myname',
    'username', 'user', 'name', 'sample', 'demo', 'test', 'testing',
    'placeholder', 'someone', 'nobody',
    'john.doe', 'johndoe', 'jane.doe', 'janedoe'
}

TEMPLATE_USERNAME_PATTERNS = [
    re.compile(r'^(your|my)[-_.]?(email|mail|name|domain|company)', re.IGNORECASE),
    re.compile(r'^(sample|demo|test|testing|placeholder|fake|template)', re.IGNORECASE),
]

INVALID_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.pdf', '.css', '.js', '.woff')

def score_email_b2b(email, website_domain=""):
    if not email or not isinstance(email, str):
        return -1
    e = email.replace('%20', '').strip().lower().rstrip('.,;:')
    if not EMAIL_REGEX.match(e):
        return -1
    u, d = e.split('@', 1)

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
    clean_domain = website_domain.lower().replace('www.', '').split('/')[0] if website_domain else ""
    if clean_domain and (clean_domain in d or d in clean_domain):
        score += 50

    # 3. ƯU TIÊN SỐ 1: Nhân sự / Tuyển dụng / Việc làm (+50đ - B2B Agency)
    if u in ['praca', 'kariera', 'hr', 'personalne', 'jobs', 'recruitment', 'nabor', 'zamestnanie', 'career', 'careers', 'talent', 'people', 'rekrutacja']:
        score += 50
    # 4. ƯU TIÊN SỐ 2: Ban Giám đốc / Lãnh đạo điều hành (+45đ)
    elif u in ['vedenie', 'riaditel', 'konatel', 'ceo', 'director', 'manager', 'obchod', 'sales', 'management', 'owner']:
        score += 45
    # 5. ƯU TIÊN SỐ 3: Cổng liên hệ chính thức / Bộ phận thông tin (+40đ)
    elif u in ['info', 'kontakt', 'contact', 'office', 'biuro', 'sekretariat', 'recepcia', 'kancelaria', 'mail']:
        score += 40
    # 6. Email đích danh cá nhân theo domain riêng (+25đ)
    elif '.' in u and score >= 60:
        score += 25
    # 7. Webmail miễn phí (+10đ - chỉ nhận nếu không có mail domain riêng)
    elif d in ['gmail.com', 'seznam.cz', 'zoznam.sk', 'post.sk', 'azet.sk']:
        score += 10
    # 8. Email kỹ thuật / hỗ trợ chung (+5đ)
    elif u in ['support', 'admin', 'help', 'webmaster']:
        score += 5

    return score

def clean_email(email_str, website=""):
    if not email_str or not isinstance(email_str, str):
        return ""
    e = email_str.replace('%20', '').strip().lower().strip(" '\"<>[],;:")
    if not e:
        return ""
    domain = urllib.parse.urlparse(website).netloc.lower().replace('www.', '') if website else ""
    parts = [p.strip(" '\"<>[],;:") for p in re.split(r'[,;\s]+', e) if p.strip(" '\"<>[],;:")]
    valid_candidates = [p for p in parts if score_email_b2b(p, domain) > 0]
    if not valid_candidates:
        return ""
    return max(valid_candidates, key=lambda p: score_email_b2b(p, domain))


def format_phone(phone_str):
    if not phone_str:
        return ""
    p = str(phone_str).strip()
    if not p:
        return ""
    # Loại bỏ ký tự thừa trừ số và dấu +
    # Nếu đã có ' ở đầu
    has_tick = p.startswith("'")
    p_clean = re.sub(r'[^\d+]', '', p)
    if not p_clean:
        return ""
    return f"'{p_clean}"

def clean_website(web_str):
    if not web_str:
        return ""
    w = str(web_str).strip()
    if not w or w.lower() in ('none', 'null', 'nan'):
        return ""
    if not (w.startswith("http://") or w.startswith("https://")):
        w = f"https://{w}"
    return w

def format_positions(job_list):
    """
    job_list: list of (position_name, quota)
    Gộp các vị trí trùng tên và tính tổng quota
    """
    if not job_list:
        return ""
    pos_counts = defaultdict(int)
    order = []
    for pos, quota in job_list:
        pos_clean = pos.strip()
        try:
            q_int = int(quota)
        except ValueError:
            q_int = 1
        if pos_clean not in pos_counts:
            order.append(pos_clean)
        pos_counts[pos_clean] += q_int

    items = [f"{p} ({pos_counts[p]})" for p in order]
    return ", ".join(items)

def main():
    if not INPUT_CSV.exists():
        print(f"[-] Không tìm thấy file: {INPUT_CSV}")
        return

    # 1. Backup file trước khi ghi
    shutil.copy2(INPUT_CSV, BACKUP_CSV)
    print(f"[*] Đã tạo bản backup tại: {BACKUP_CSV}")

    # 2. Đọc DMW Job orders chi tiết
    jobs_per_principal = defaultdict(list)
    agencies_per_principal = defaultdict(list)
    if DMW_ORDERS.exists():
        with open(DMW_ORDERS, 'r', encoding='utf-8-sig', errors='ignore') as f:
            for row in csv.DictReader(f):
                p = row.get('Principal', '').strip()
                pos = row.get('Position', '').strip()
                bal = row.get('Balance', '').replace("'", "").strip()
                agency = row.get('Agency', '').strip()
                if pos:
                    jobs_per_principal[p].append((pos, bal))
                if agency and agency not in agencies_per_principal[p]:
                    agencies_per_principal[p].append(agency)

    # 3. Đọc DMW Aggregated data (chứa Website, Address gốc)
    agg_data = {}
    if DMW_AGG.exists():
        with open(DMW_AGG, 'r', encoding='utf-8-sig', errors='ignore') as f:
            for row in csv.DictReader(f):
                p = row.get('Principal', '').strip()
                if p:
                    agg_data[p] = row

    # 4. Đọc Maps Cache
    maps_cache = {}
    if MAPS_CACHE.exists():
        try:
            with open(MAPS_CACHE, 'r', encoding='utf-8-sig', errors='ignore') as f:
                maps_cache = json.load(f)
        except Exception:
            pass

    # 5. Đọc danh sách doanh nghiệp từ slovakiaphilip_backup_before_maps.csv (đảm bảo đúng cấu trúc gốc)
    SOURCE_RAW_CSV = ROOT_DIR / "slovakiaphilip_backup_before_maps.csv"
    if not SOURCE_RAW_CSV.exists():
        SOURCE_RAW_CSV = INPUT_CSV

    with open(SOURCE_RAW_CSV, 'r', encoding='utf-8-sig', errors='ignore') as f:
        reader = csv.DictReader(f)
        raw_rows = list(reader)

    print(f"[*] Đọc {len(raw_rows)} doanh nghiệp từ {SOURCE_RAW_CSV.name}")

    output_rows = []
    total_emails = 0
    total_phones = 0
    total_websites = 0
    total_addresses = 0
    check_gui_count = 0

    for idx, r in enumerate(raw_rows, 1):
        principal = (r.get("Principal") or r.get("Công ty") or "").strip()
        quota = (r.get("Total_Recruitment_Quota") or "").replace("'", "").strip()
        phone_raw = (r.get("Phone") or r.get("SĐT") or "").strip()
        email_raw = (r.get("Email") or "").strip()
        date_approved = (r.get("Latest_Date_Approved") or r.get("Ngày đăng") or "").strip()
        website_raw = (r.get("Website") or r.get("Liên Hệ") or "").strip()
        address_raw = (r.get("Address") or r.get("Địa chỉ") or "").strip()
        agencies_raw = (r.get("Philippine_Agencies") or r.get("Người liên hệ") or "").strip()

        # Kiểm tra ghi chú đặc biệt (ví dụ ALZA từ chối)
        is_rejected = "ALZA" in principal.upper()

        # Lấy thêm từ agg_data nếu có
        agg = agg_data.get(principal, {})
        website_agg = agg.get('Website', '').strip()
        address_agg = agg.get('Address', '').strip()
        agencies_agg = agg.get('Philippine_Agencies', '').strip()

        # Lấy từ Maps Cache nếu có
        m_info = maps_cache.get(principal.upper(), {})
        if not isinstance(m_info, dict) or m_info.get("not_found"):
            m_info = {}

        m_phone = m_info.get("phone", "")
        m_web = m_info.get("website", "")
        m_addr = m_info.get("address", "")


        # Ưu tiên dữ liệu tốt nhất
        # 1. Phone
        phone = format_phone(phone_raw or agg.get('Phone') or m_phone)
        if phone:
            total_phones += 1

        # 2. Website
        website = clean_website(website_raw or website_agg or m_web)
        if website:
            total_websites += 1

        # 3. Email (Scored & 1 best email selected)
        email = clean_email(email_raw or agg.get('Email'), website)
        if "TATRY MOUNTAIN RESORTS" in principal.upper() and not email:
            email = "info@vt.sk"
        if email:
            total_emails += 1

        # 4. Address
        address = address_raw or address_agg or m_addr
        if address:
            # Làm sạch ký tự lạ nếu có
            address = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', address).strip()
            total_addresses += 1

        # 5. Chức danh (Positions)
        job_list = jobs_per_principal.get(principal, [])
        positions_str = format_positions(job_list)

        # 6. Người liên hệ / Đối tác phái cử Philippines
        agencies = agencies_per_principal.get(principal, [])
        if agencies:
            agency_str = "; ".join(agencies)
        else:
            agency_str = agencies_raw or agencies_agg

        # 7. Check gửi & Trạng thái Reply
        check_gui = ""
        reply_status = ""

        if is_rejected:
            reply_status = "Đã từ chối"
            check_gui = ""
        elif email:
            check_gui = "OK"
            check_gui_count += 1

        # 8. Category
        order_count = len(job_list) if job_list else 1
        cat_str = f"Tuyển lao động Philippines - Hạn ngạch: {quota} chỉ tiêu ({order_count} đơn hàng)"

        row_dict = {
            "No.": idx,
            "Công ty": principal,
            "Chức danh": positions_str,
            "Người liên hệ": agency_str,
            "SĐT": phone,
            "Liên Hệ": website,
            "Email": email,
            "Liên Hệ mail": "",
            "Địa chỉ": address,
            "Lương": "",
            "Ngày đăng": date_approved,
            "Hạn tuyển": "",
            "Check gửi": check_gui,
            "Last Subject": "",
            "Last Body HTML": "",
            "Trạng thái Reply": reply_status,
            "Lần Follow-up": 0,
            "Ngày Follow-up gần nhất": "",
            "Mailbox đã dùng": "",
            "Category": cat_str
        }
        output_rows.append(row_dict)

    # 6. Ghi ra cả 2 file:
    # 6.1. slovakiaphilip_ColdMail.csv
    with open(OUTPUT_COLDMAIL_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(output_rows)

    # 6.2. Cập nhật trực tiếp slovakiaphilip.csv theo đúng yêu cầu người dùng
    with open(INPUT_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(output_rows)

    print("\n" + "=" * 70)
    print("HOÀN TẤT CHUYỂN ĐỔI MẪU COLD MAIL CHO SLOVAKIAPHILIP!")
    print(f"Tổng số công ty: {len(output_rows)}")
    print(f"Số công ty có Email hợp lệ (Check gửi = 'OK'): {check_gui_count}/{len(output_rows)} ({check_gui_count/len(output_rows)*100:.1f}%)")
    print(f"Số công ty có SĐT: {total_phones}/{len(output_rows)} ({total_phones/len(output_rows)*100:.1f}%)")
    print(f"Số công ty có Website: {total_websites}/{len(output_rows)} ({total_websites/len(output_rows)*100:.1f}%)")
    print(f"Số công ty có Địa chỉ: {total_addresses}/{len(output_rows)} ({total_addresses/len(output_rows)*100:.1f}%)")
    print("=" * 70)
    print(f"[+] Đã cập nhật trực tiếp: {INPUT_CSV}")
    print(f"[+] Đã xuất file Cold Mail: {OUTPUT_COLDMAIL_CSV}")
    print(f"[+] Bản backup trước chuyển đổi: {BACKUP_CSV}")

if __name__ == "__main__":
    main()
