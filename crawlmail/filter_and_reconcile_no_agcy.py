# -*- coding: utf-8 -*-
"""
HỆ THỐNG ĐỐI CHIẾU, LÀM SẠCH VÀ LÀM GIÀU DỮ LIỆU AGENCY NA UY (NORWAY 2COL)
-----------------------------------------------------------------------------------
Mục tiêu xử lý:
1. Đối chiếu giữa NO_AGCY_WEBD_2COL.csv và (xong 9_29) môi giới na uy - CleanData.csv:
   - Bổ sung toàn bộ các công ty chưa có từ CleanData vào danh sách mới.
   - Đối soát làm giàu Email, SĐT, Website, Người liên hệ, Địa chỉ cho các công ty chưa có mail.
2. Loại bỏ triệt để Mail Bounce:
   - Rà soát 182 email bounce ghi nhận từ chiến dịch cũ trong CleanData.
   - Rà soát các email bounce/hỏng trong Mail Tracker.
3. So khớp Mail Tracker và loại bỏ Mail Đã Phản Hồi:
   - Rà soát toàn bộ các đơn vị đã phản hồi (Replied, Quan tâm, Từ chối, Không cần).
   - Loại trừ theo Email, Corporate Domain và Tên công ty chuẩn hóa.
4. Lọc trùng lặp nghiêm ngặt (Strict Deduplication):
   - Khử trùng theo Tên công ty chuẩn hóa (loại bỏ legal form AS, ASA, NUF, group, holding...).
   - RÀNG BUỘC DUY NHẤT: Mỗi Email chỉ xuất hiện DUY NHẤT 1 LẦN trong tệp Cold Mail 2COL.
5. Loại trừ danh sách đen vĩnh viễn (Scandi Standard, Biliarta, Daigre per GEMINI.md).
6. Định dạng chuẩn hóa Cold Mail 20 cột (GEMINI.md Rule 3 & data-standards):
   - Đẩy 100% doanh nghiệp có Email lên các dòng đầu tiên (1..N).
   - Đánh lại số thứ tự No. liên tục từ 1 đến hết.
   - SĐT có nháy đơn (') và mã vùng Na Uy +47 ('+47 ...).
   - Xuất file UTF-8 with BOM (utf-8-sig) và lưu file audit các bản ghi đã loại bỏ.
"""

import sys
import os
import re
import shutil
import urllib.parse
import unicodedata
from pathlib import Path
import pandas as pd

# Cấu hình UTF-8 cho Windows Console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

FILE_2COL = ROOT_DIR / "NO_AGCY_WEBD_2COL.csv"
FILE_CLEANDATA = ROOT_DIR / "(xong 9_29) môi giới na uy - CleanData.csv"
FILE_TRACKER = ROOT_DIR / "Mail Tracker - mail.csv"

BACKUP_2COL = ROOT_DIR / "NO_AGCY_WEBD_2COL_pre_merge_backup.csv"
BACKUP_CLEANDATA = ROOT_DIR / "(xong 9_29) môi giới na uy - CleanData_pre_filter_backup.csv"

OUT_AUDIT_CSV = ROOT_DIR / "archive" / "no_norway" / "NO_AGCY_DA_LOAI_BO_REPLY_BOUNCE.csv"
CSDL_2COL = ROOT_DIR / "csdl_mlt" / "NO_AGCY_WEBD_2COL.csv"
ARCHIVE_2COL = ROOT_DIR / "archive" / "no_norway" / "NO_AGCY_WEBD_2COL.csv"

COLUMNS_20 = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

GENERIC_DOMS = {
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
    'online.no', 'live.no', 'mail.com', 'icloud.com', 'lyse.net', 'broadpark.no'
}

PERMANENT_BLACKLIST = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre', 'daigre'
]

def clean_phone_no(phone_raw):
    """Chuẩn hóa số điện thoại Na Uy (+47) và thêm dấu nháy đơn (')"""
    if not phone_raw:
        return ""
    p = str(phone_raw).strip()
    if p in ['', 'None', 'nan', 'null']:
        return ""
    digits = re.sub(r'[^\d+]', '', p)
    if digits.startswith('+47'):
        formatted = f"+47 {digits[3:]}"
    elif digits.startswith('47') and len(digits) == 10:
        formatted = f"+47 {digits[2:]}"
    elif len(digits) == 8:
        formatted = f"+47 {digits}"
    else:
        formatted = p
    return f"'{formatted}" if not formatted.startswith("'") else formatted

def clean_email(email_raw):
    """Làm sạch email triệt để theo quy chuẩn bắt buộc GEMINI.md & data-standards"""
    if not email_raw:
        return ""
    em = str(email_raw).strip().lower()
    em = em.replace('%20', '').replace('\u00a0', '').replace('\xa0', '').replace('&nbsp;', '')
    em = re.sub(r'[\s\u200b\ufeff]', '', em)
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', em):
        return ""
    
    bad_prefixes = ['youremail', 'your-email', 'yourname', 'someone', 'john.doe', 'example', 'name@', 'email@', 'user@']
    bad_domains = ['example.com', 'domain.com', 'company.com', 'email.com', 'sentry.io', 'wixpress.com', 'wordpress.com']
    
    if any(em.startswith(b) for b in bad_prefixes) or any(em.endswith(b) for b in bad_domains):
        return ""
    if any(k in em for k in ['sentry', 'wix', 'wordpress', 'no-reply', 'donotreply', 'privacy', 'gdpr']):
        return ""
        
    return em

def norm_name(name):
    """Chuẩn hóa tên công ty loại bỏ các loại hình pháp lý Na Uy để so khớp chính xác"""
    if not name:
        return ""
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    legal = r'\b(as|asa|ans|da|enk|nuf|kf|iks|sa|holding|group|norge|norway)\b'
    n_clean = re.sub(legal, ' ', n_clean)
    n_clean = re.sub(r'[^a-z0-9]', ' ', n_clean)
    return ' '.join(n_clean.split())

def is_blacklisted(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST)

def get_domain(url):
    if not url:
        return ""
    u = str(url).strip()
    if not u.startswith('http'):
        u = 'https://' + u
    try:
        p = urllib.parse.urlparse(u)
        netloc = p.netloc.lower()
        if netloc.startswith('www.'):
            netloc = netloc[4:]
        if netloc in ['facebook.com', 'linkedin.com', 'instagram.com', 'google.com', 'proff.no', 'gulesider.no', 'yellowpages']:
            return ""
        return netloc
    except Exception:
        return ""

def main():
    print("=" * 80)
    print(" ĐỐI CHIẾU, LÀM SẠCH & LÀM GIÀU DỮ LIỆU AGENCY NA UY (NORWAY 2COL)")
    print(" LOẠI BỎ BOUNCE, SO KHỚP MAIL TRACKER & KHỬ TRÙNG LẶP TOÀN BỘ")
    print("=" * 80)

    if not FILE_2COL.exists() or not FILE_CLEANDATA.exists():
        print(f"[-] Lỗi: Không tìm thấy file đầu vào:")
        print(f"    - {FILE_2COL}")
        print(f"    - {FILE_CLEANDATA}")
        return

    # 1. Tạo backup an toàn cho cả 2 tệp
    shutil.copy2(FILE_2COL, BACKUP_2COL)
    shutil.copy2(FILE_CLEANDATA, BACKUP_CLEANDATA)
    print(f"[+] Đã tạo backup:")
    print(f"    - {BACKUP_2COL.name}")
    print(f"    - {BACKUP_CLEANDATA.name}")

    # 2. Nạp Mail Tracker (để nhận diện mail phản hồi, từ chối, quan tâm)
    tracker_emails = {}
    tracker_domains = {}
    tracker_companies = {}

    if FILE_TRACKER.exists():
        df_tr = pd.read_csv(FILE_TRACKER, encoding='utf-8-sig', dtype=str).fillna('')
        for idx, r in df_tr.iterrows():
            sender = r.get('Người gửi', '').strip().lower()
            subj = r.get('Subject', '').strip()
            content = r.get('Nội dung', '').strip()
            status = r.get('Tình trạng phản hồi', '').strip()
            note = r.get('Note', '').strip()
            desc = status if status else (note if note else subj[:35])

            for em in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', f"{sender} {subj} {content} {note}".lower()):
                if not any(k in em for k in ['glcquocte', 'workforce.asia', 'mobilityworks.asia', 'vietnammanpower.asia']):
                    tracker_emails[em] = f"Tracker Email: {em} ({desc})"
                    d = em.split('@')[-1]
                    if d not in GENERIC_DOMS:
                        tracker_domains[d] = f"Tracker Domain: @{d} ({desc})"

            for txt in [note, subj]:
                n_comp = norm_name(txt)
                if len(n_comp) >= 5 and not any(k in n_comp for k in ['re asian', 're labor', 're reliable', 'fwd', 're personnel', 're nail']):
                    tracker_companies[n_comp] = f"Tracker Company: '{txt[:30]}' ({desc})"

        print(f"[+] Đã nạp từ Mail Tracker: {len(tracker_emails):,} emails, {len(tracker_domains):,} corporate domains.")
    else:
        print(f"[!] Không tìm thấy file: {FILE_TRACKER}")

    # 3. Phân loại Mail Bounce và Mail Reply trong CleanData (9_29)
    df_old = pd.read_csv(FILE_CLEANDATA, encoding='utf-8-sig', dtype=str).fillna('')
    total_old = len(df_old)
    print(f"[*] Tổng số doanh nghiệp trong CleanData (9_29): {total_old:,}")

    bounced_emails = set()
    replied_emails = set()
    removed_audit = []

    for idx, r in df_old.iterrows():
        comp = r.get('Công ty', '').strip()
        em = clean_email(r.get('Email', ''))
        rep = r.get('Trạng thái Reply', '').strip().lower()

        if 'bounce' in rep or 'lỗi' in rep or 'không dùng được' in rep:
            if em:
                bounced_emails.add(em)
            removed_audit.append({
                'Công ty': comp,
                'Email': em,
                'SĐT': r.get('SĐT', ''),
                'Web': r.get('Liên Hệ', ''),
                'Nguồn': 'CleanData (9_29)',
                'Lý do loại bỏ': f"Bounce trong CleanData: {r.get('Trạng thái Reply')}"
            })
        elif 'reply' in rep or 'phản hồi' in rep:
            if em:
                replied_emails.add(em)
            removed_audit.append({
                'Công ty': comp,
                'Email': em,
                'SĐT': r.get('SĐT', ''),
                'Web': r.get('Liên Hệ', ''),
                'Nguồn': 'CleanData (9_29)',
                'Lý do loại bỏ': f"Đã phản hồi trong CleanData: {r.get('Trạng thái Reply')}"
            })

    print(f"[+] Phát hiện: {len(bounced_emails):,} email bounce & {len(replied_emails):,} email đã phản hồi trong CleanData.")

    # 4. Xây dựng bản đồ tra cứu từ CleanData (đã loại bỏ sạch bounce/reply)
    old_lookup_name = {}
    old_lookup_domain = {}

    for idx, r in df_old.iterrows():
        comp = r.get('Công ty', '').strip()
        c_norm = norm_name(comp)
        em = clean_email(r.get('Email', ''))
        web = r.get('Liên Hệ', '').strip()
        dom = get_domain(web)
        rep = r.get('Trạng thái Reply', '').strip().lower()

        # Bỏ qua hoàn toàn các dòng bounce / reply / blacklist
        if 'bounce' in rep or 'lỗi' in rep or 'không dùng được' in rep or 'reply' in rep or 'phản hồi' in rep:
            continue
        if em in bounced_emails or em in replied_emails or em in tracker_emails:
            continue
        if is_blacklisted(comp):
            continue

        # Nếu chưa có web nhưng có mail theo tên miền riêng, suy ra web
        if not web and em and '@' in em:
            em_dom = em.split('@')[-1]
            if em_dom not in GENERIC_DOMS:
                web = f"https://{em_dom}"
                dom = em_dom

        row_data = {
            'Công ty': comp,
            'Chức danh': r.get('Chức danh', ''),
            'Người liên hệ': r.get('Người liên hệ', ''),
            'SĐT': clean_phone_no(r.get('SĐT', '')),
            'Liên Hệ': web,
            'Email': em,
            'Địa chỉ': r.get('Địa chỉ', ''),
            'Category': r.get('Category', '') or 'Rekruttering og bemanning (Norway)'
        }

        if c_norm and c_norm not in old_lookup_name:
            old_lookup_name[c_norm] = row_data
        if dom and dom not in old_lookup_domain:
            old_lookup_domain[dom] = row_data

    print(f"[+] Bản đồ tra cứu sạch CleanData: {len(old_lookup_name):,} theo tên, {len(old_lookup_domain):,} theo domain.")

    # 5. Đọc file NO_AGCY_WEBD_2COL.csv hiện tại và đối soát làm giàu
    df_new = pd.read_csv(FILE_2COL, encoding='utf-8-sig', dtype=str).fillna('')
    total_new = len(df_new)
    print(f"[*] Tổng số doanh nghiệp trong 2COL hiện tại: {total_new:,}")

    combined_pool = []
    matched_old_names = set()
    matched_old_doms = set()
    enriched_emails = 0
    enriched_phones = 0
    enriched_webs = 0

    for idx, r in df_new.iterrows():
        comp = r.get('Công ty', '').strip()
        c_norm = norm_name(comp)
        em = clean_email(r.get('Email', ''))
        web = r.get('Liên Hệ', '').strip()
        dom = get_domain(web)
        phone = clean_phone_no(r.get('SĐT', ''))
        leader = r.get('Người liên hệ', '').strip()
        role = r.get('Chức danh', '').strip()
        addr = r.get('Địa chỉ', '').strip()
        cat = r.get('Category', '').strip()

        # Kiểm tra Blacklist
        if is_blacklisted(comp):
            removed_audit.append({'Công ty': comp, 'Email': em, 'SĐT': phone, 'Web': web, 'Nguồn': '2COL', 'Lý do loại bỏ': 'Hard Blacklist'})
            continue

        # Kiểm tra Reply trong Tracker
        if em and em in tracker_emails:
            removed_audit.append({'Công ty': comp, 'Email': em, 'SĐT': phone, 'Web': web, 'Nguồn': '2COL', 'Lý do loại bỏ': tracker_emails[em]})
            continue
        if em and '@' in em and em.split('@')[-1] in tracker_domains:
            d = em.split('@')[-1]
            removed_audit.append({'Công ty': comp, 'Email': em, 'SĐT': phone, 'Web': web, 'Nguồn': '2COL', 'Lý do loại bỏ': tracker_domains[d]})
            continue
        if c_norm in tracker_companies:
            removed_audit.append({'Công ty': comp, 'Email': em, 'SĐT': phone, 'Web': web, 'Nguồn': '2COL', 'Lý do loại bỏ': tracker_companies[c_norm]})
            continue

        # Kiểm tra Bounce
        if em and em in bounced_emails:
            em = '' # Xóa bỏ email hỏng/bounce

        # Đối soát & làm giàu từ CleanData (9_29)
        match_ref = None
        if c_norm in old_lookup_name:
            match_ref = old_lookup_name[c_norm]
            matched_old_names.add(c_norm)
        elif dom in old_lookup_domain:
            match_ref = old_lookup_domain[dom]
            matched_old_doms.add(dom)

        if match_ref:
            if not em and match_ref.get('Email'):
                cand_em = match_ref['Email']
                if cand_em not in bounced_emails and cand_em not in tracker_emails:
                    em = cand_em
                    enriched_emails += 1
            if not phone and match_ref.get('SĐT'):
                phone = match_ref['SĐT']
                enriched_phones += 1
            if not web and match_ref.get('Liên Hệ'):
                web = match_ref['Liên Hệ']
                enriched_webs += 1
            if not leader and match_ref.get('Người liên hệ'):
                leader = match_ref['Người liên hệ']
                role = match_ref.get('Chức danh') or 'Daglig leder'
            if not addr and match_ref.get('Địa chỉ'):
                addr = match_ref['Địa chỉ']

        # Nếu vẫn thiếu web nhưng có mail theo domain riêng
        if not web and em and '@' in em:
            em_dom = em.split('@')[-1]
            if em_dom not in GENERIC_DOMS:
                web = f"https://{em_dom}"

        combined_pool.append({
            'Công ty': comp,
            'Chức danh': role if role else 'Daglig leder',
            'Người liên hệ': leader,
            'SĐT': phone,
            'Liên Hệ': web,
            'Email': em,
            'Địa chỉ': addr,
            'Category': cat if cat else 'Rekruttering og bemanning (Norway)'
        })

    print(f"[+] Đối soát làm giàu cho 2COL: +{enriched_emails:,} Email, +{enriched_phones:,} SĐT, +{enriched_webs:,} Website.")

    # 6. Bổ sung các công ty từ CleanData chưa có trong 2COL
    added_from_cleandata = 0
    for idx, r in df_old.iterrows():
        comp = r.get('Công ty', '').strip()
        c_norm = norm_name(comp)
        web = r.get('Liên Hệ', '').strip()
        dom = get_domain(web)
        em = clean_email(r.get('Email', ''))
        rep = r.get('Trạng thái Reply', '').strip().lower()

        if 'bounce' in rep or 'lỗi' in rep or 'không dùng được' in rep or 'reply' in rep or 'phản hồi' in rep:
            continue
        if em in bounced_emails or em in replied_emails or em in tracker_emails:
            continue
        if is_blacklisted(comp):
            continue

        # Nếu đã có trong 2COL thì bỏ qua (tránh lặp)
        if c_norm in matched_old_names or (dom and dom in matched_old_doms):
            continue

        if em and '@' in em and em.split('@')[-1] in tracker_domains:
            continue
        if c_norm in tracker_companies:
            continue

        phone = clean_phone_no(r.get('SĐT', ''))
        leader = r.get('Người liên hệ', '').strip()
        role = r.get('Chức danh', '').strip()
        addr = r.get('Địa chỉ', '').strip()
        cat = r.get('Category', '').strip()

        if not web and em and '@' in em:
            em_dom = em.split('@')[-1]
            if em_dom not in GENERIC_DOMS:
                web = f"https://{em_dom}"

        combined_pool.append({
            'Công ty': comp,
            'Chức danh': role if role else 'Daglig leder',
            'Người liên hệ': leader,
            'SĐT': phone,
            'Liên Hệ': web,
            'Email': em,
            'Địa chỉ': addr,
            'Category': cat if cat else 'Rekruttering og bemanning (Norway)'
        })
        added_from_cleandata += 1
        if c_norm:
            matched_old_names.add(c_norm)
        if dom:
            matched_old_doms.add(dom)

    print(f"[+] Bổ sung thêm công ty mới từ CleanData chưa có trong 2COL: +{added_from_cleandata:,}")
    print(f"[*] Tổng số lượng doanh nghiệp gộp trước khi khử trùng lặp: {len(combined_pool):,}")

    # 7. Khử trùng lặp đa tầng (Deduplication)
    # Lớp 1: Khử trùng theo tên chuẩn hóa
    seen_comp_names = {}
    dedup_by_name = []
    for c in combined_pool:
        c_norm = norm_name(c['Công ty'])
        if not c_norm:
            dedup_by_name.append(c)
            continue
        if c_norm not in seen_comp_names:
            seen_comp_names[c_norm] = len(dedup_by_name)
            dedup_by_name.append(c)
        else:
            prev_idx = seen_comp_names[c_norm]
            prev_c = dedup_by_name[prev_idx]
            # Hợp nhất giữ thông tin đầy đủ nhất
            if not prev_c['Email'] and c['Email']:
                prev_c['Email'] = c['Email']
            if not prev_c['SĐT'] and c['SĐT']:
                prev_c['SĐT'] = c['SĐT']
            if not prev_c['Liên Hệ'] and c['Liên Hệ']:
                prev_c['Liên Hệ'] = c['Liên Hệ']
            if not prev_c['Người liên hệ'] and c['Người liên hệ']:
                prev_c['Người liên hệ'] = c['Người liên hệ']
                prev_c['Chức danh'] = c['Chức danh']
            if not prev_c['Địa chỉ'] and c['Địa chỉ']:
                prev_c['Địa chỉ'] = c['Địa chỉ']

    print(f"[+] Sau khi khử trùng lặp theo tên chuẩn hóa: còn {len(dedup_by_name):,} doanh nghiệp.")

    # Lớp 2: Ràng buộc UNIQUE EMAIL 100% cho tệp Cold Mail
    unique_emails = set()
    with_email_rows = []
    without_email_rows = []

    for c in dedup_by_name:
        em = c['Email']
        if em:
            if em not in unique_emails:
                unique_emails.add(em)
                with_email_rows.append(c)
            else:
                # Nếu email bị trùng với công ty đã có trước, gỡ mail để không spam trùng
                c_no_em = dict(c)
                c_no_em['Email'] = ''
                without_email_rows.append(c_no_em)
        else:
            without_email_rows.append(c)

    print(f"[+] Tổng số doanh nghiệp CÓ EMAIL DUY NHẤT (100% Unique): {len(with_email_rows):,}")
    print(f"[+] Tổng số doanh nghiệp CHƯA CÓ EMAIL                 : {len(without_email_rows):,}")
    
    # 8. Chuẩn hóa format Cold Mail 20 cột (Đẩy 100% Email lên đầu)
    all_final_sorted = with_email_rows + without_email_rows
    final_output_rows = []

    for idx, r in enumerate(all_final_sorted, 1):
        em = r['Email']
        final_output_rows.append({
            'No.': str(idx),
            'Công ty': r['Công ty'],
            'Chức danh': r['Chức danh'],
            'Người liên hệ': r['Người liên hệ'],
            'SĐT': r['SĐT'],
            'Liên Hệ': r['Liên Hệ'],
            'Email': em,
            'Liên Hệ mail': f"mailto:{em}" if em else '',
            'Địa chỉ': r['Địa chỉ'],
            'Lương': '',
            'Ngày đăng': '',
            'Hạn tuyển': '',
            'Check gửi': 'Da_Gui_Truoc' if em else '',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trạng thái Reply': '',
            'Lần Follow-up': '0' if em else '',
            'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': r['Category']
        })

    df_final = pd.DataFrame(final_output_rows, columns=COLUMNS_20)

    # 9. Ghi đè vào các file đích chuẩn UTF-8 with BOM
    df_final.to_csv(FILE_2COL, index=False, encoding='utf-8-sig')
    print(f"[*] Đã xuất bản tệp chuẩn Cold Mail: {FILE_2COL.name}")

    # Đồng bộ vào CleanData gốc
    df_final.to_csv(FILE_CLEANDATA, index=False, encoding='utf-8-sig')
    print(f"[*] Đã đồng bộ vào tệp CleanData gốc: {FILE_CLEANDATA.name}")

    # Đồng bộ csdl_mlt và archive
    CSDL_2COL.parent.mkdir(parents=True, exist_ok=True)
    df_final.to_csv(CSDL_2COL, index=False, encoding='utf-8-sig')
    print(f"[*] Đã đồng bộ vào: {CSDL_2COL}")

    ARCHIVE_2COL.parent.mkdir(parents=True, exist_ok=True)
    df_final.to_csv(ARCHIVE_2COL, index=False, encoding='utf-8-sig')
    print(f"[*] Đã đồng bộ vào: {ARCHIVE_2COL}")

    # 10. Xuất file Audit các bản ghi đã loại bỏ
    if removed_audit:
        df_audit = pd.DataFrame(removed_audit)
        OUT_AUDIT_CSV.parent.mkdir(parents=True, exist_ok=True)
        df_audit.to_csv(OUT_AUDIT_CSV, index=False, encoding='utf-8-sig')
        print(f"[*] Đã xuất file nhật ký loại bỏ (Audit log): {OUT_AUDIT_CSV} ({len(df_audit):,} bản ghi)")

    print("\n" + "=" * 80)
    print(" HOÀN TẤT ĐỐI CHIẾU, LÀM SẠCH VÀ LÀM GIÀU AGENCY NA UY THÀNH CÔNG!")
    print(f" [*] Tổng số doanh nghiệp cuối cùng       : {len(df_final):,}")
    print(f" [*] Tổng số doanh nghiệp CÓ EMAIL B2B     : {len(with_email_rows):,} (Đẩy 100% lên đầu)")
    print(f" [*] Đã loại bỏ email bounce & reply      : {len(bounced_emails) + len(replied_emails):,}")
    print(f" [*] File kết quả Cold Mail sẵn sàng gửi  : {FILE_2COL.name}")
    print("=" * 80 + "\n")

if __name__ == '__main__':
    main()

