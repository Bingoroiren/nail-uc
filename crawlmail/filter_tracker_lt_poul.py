# -*- coding: utf-8 -*-
"""
ĐỐI CHIẾU & LÀM SẠCH LT_POUL_WEBD_2COL.csv VỚI MAIL TRACKER
------------------------------------------------------------
Mục tiêu:
1. Đối chiếu toàn diện tệp thịt gà Litva (LT_POUL_WEBD_2COL.csv) với:
   - Mail Tracker - mail.csv (trạng thái 'Đã phản hồi', 'Không cần', 'Blacklist')
   - archive/lt_lithuania/LT_FOOD_DA_LOAI_BO_REPLY_BOUNCE.csv (danh sách đã reply & bounce từ food)
   - archive/lt_lithuania/LT_POUL_DA_LOAI_BO_REPLY_BOUNCE.csv (danh sách 24 bounce đã lọc)
2. Loại bỏ 100% công ty đã phản hồi hoặc nằm trong Hard Blacklist (Scandi Standard, Biliarta, Daigre per GEMINI.md).
3. Đảm bảo chuẩn 20 cột Cold Mail:
   - 100% công ty có Email xếp ở các dòng đầu tiên.
   - SĐT có nháy đơn (') ở đầu.
   - UTF-8 with BOM (utf-8-sig).
4. Đồng bộ file vào:
   - LT_POUL_WEBD_2COL.csv
   - csdl_mlt/LT_POUL_WEBD_2COL.csv
   - archive/lt_lithuania/LT_POUL_WEBD_2COL.csv
"""

import sys
import os
import re
import shutil
import unicodedata
import pandas as pd
from pathlib import Path

# Cấu hình UTF-8 cho Windows Console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

TARGET_CSV = ROOT_DIR / "LT_POUL_WEBD_2COL.csv"
CSDL_CSV = ROOT_DIR / "csdl_mlt" / "LT_POUL_WEBD_2COL.csv"
ARCHIVE_CSV = ROOT_DIR / "archive" / "lt_lithuania" / "LT_POUL_WEBD_2COL.csv"

FILE_TRACKER = ROOT_DIR / "Mail Tracker - mail.csv"
FOOD_AUDIT_CSV = ROOT_DIR / "archive" / "lt_lithuania" / "LT_FOOD_DA_LOAI_BO_REPLY_BOUNCE.csv"
POUL_BOUNCE_CSV = ROOT_DIR / "archive" / "lt_lithuania" / "LT_POUL_DA_LOAI_BO_REPLY_BOUNCE.csv"
OUT_AUDIT_CSV = ROOT_DIR / "archive" / "lt_lithuania" / "LT_POUL_DA_LOAI_BO_REPLY_TRACKER.csv"

COLUMNS_20 = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

GENERIC_DOMS = {
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'icloud.com',
    'centrum.sk', 'centrum.cz', 'zoznam.sk', 'post.sk', 'azet.sk', 'seznam.cz',
    'inbox.lt', 'inbox.lv', 'mail.ru', 'yandex.ru', 'email.cz', 'takas.lt',
    'glcquocte.com.vn', 'workforce.asia', 'mobilityworks.asia', 'vietnammanpower.asia', 'workbridge.asia'
}

PERMANENT_BLACKLIST = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre', 'daigre'
]

def clean_phone(p):
    if not p or str(p).strip() == '' or str(p) == 'nan':
        return ''
    s = str(p).strip()
    return f"'{s}" if not s.startswith("'") else s

def norm_name(name):
    if not name:
        return ""
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    for legal in ['uzdaroji akcine bendrove', 'mazoji bendrija', 'akcine bendrove', 'viesoji istaiga',
                  'zemes ukio kooperatine bendrove', 'uab', 'mb', 'vsi', 'ab', 'ii', 'zukb', 's.r.o.', 'a.s.', 'gmbh']:
        n_clean = re.sub(rf'\b{legal}\b', '', n_clean)
    n_clean = re.sub(r'[^a-z0-9]', ' ', n_clean)
    return ' '.join(n_clean.split())

def is_blacklisted(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST)

def main():
    print("=" * 80)
    print(" ĐỐI CHIẾU & LÀM SẠCH LT_POUL_WEBD_2COL.csv VỚI MAIL TRACKER")
    print(" LOẠI BỎ CÔNG TY ĐÃ PHẢN HỒI (REPLIED) / HARD BLACKLIST / BOUNCE")
    print("=" * 80)

    if not TARGET_CSV.exists():
        print(f"[-] Không tìm thấy tệp mục tiêu: {TARGET_CSV}")
        return

    # 1. Nạp Mail Tracker
    tracker_replied_emails = {}
    tracker_replied_domains = {}
    tracker_replied_companies = {}

    if FILE_TRACKER.exists():
        df_tr = pd.read_csv(FILE_TRACKER, encoding='utf-8-sig', dtype=str).fillna('')
        for idx, r in df_tr.iterrows():
            sender = r.get('Người gửi', '').strip().lower()
            subj = r.get('Subject', '').strip()
            content = r.get('Nội dung', '').strip()
            status = r.get('Tình trạng phản hồi', '').strip()
            note = r.get('Note', '').strip()
            
            # Chỉ xét các phản hồi hoặc blacklist
            is_reply = status in ['Đã phản hồi', 'Không cần'] or 'blacklist' in note.lower()
            if not is_reply:
                continue

            desc = f"{status} (Note: {note})" if note else status
            
            # Email từ Người gửi
            if sender and '@' in sender:
                tracker_replied_emails[sender] = f"Tracker Sender: {sender} ({desc})"
                d = sender.split('@')[-1]
                if d not in GENERIC_DOMS:
                    tracker_replied_domains[d] = f"Tracker Domain: @{d} ({desc})"

            # Email từ nội dung / subject
            for em in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', f"{subj} {content} {note}".lower()):
                if not any(k in em for k in ['glcquocte', 'workforce.asia', 'mobilityworks.asia', 'vietnammanpower.asia', 'workbridge.asia']):
                    tracker_replied_emails[em] = f"Tracker Content Email: {em} ({desc})"
                    d = em.split('@')[-1]
                    if d not in GENERIC_DOMS:
                        tracker_replied_domains[d] = f"Tracker Domain: @{d} ({desc})"

            # Tên công ty ghi trong Note hoặc Signature
            for txt in [note]:
                n_comp = norm_name(txt)
                if len(n_comp) >= 5 and not any(k in n_comp for k in ['re asian', 're labor', 're reliable', 'fwd', 'personnel', 'workforce', 'blacklist']):
                    tracker_replied_companies[n_comp] = f"Tracker Company in Note: '{txt[:40]}' ({desc})"

        print(f"[+] Đã nạp từ Mail Tracker: {len(tracker_replied_emails):,} emails & {len(tracker_replied_domains):,} corporate domains phản hồi.")
    else:
        print(f"[!] Không tìm thấy file: {FILE_TRACKER}")

    # 2. Nạp thêm danh sách đã phản hồi từ LT_FOOD_DA_LOAI_BO_REPLY_BOUNCE.csv
    if FOOD_AUDIT_CSV.exists():
        df_food_audit = pd.read_csv(FOOD_AUDIT_CSV, encoding='utf-8-sig', dtype=str).fillna('')
        replied_food = df_food_audit[df_food_audit['Lý do loại bỏ'].str.contains('phản hồi|reply|từ chối|không cần', case=False, na=False)]
        for _, r in replied_food.iterrows():
            em = r.get('Email', '').strip().lower()
            c_name = r.get('Công ty', '').strip()
            reason = r.get('Lý do loại bỏ', '').strip()
            if em and '@' in em:
                tracker_replied_emails[em] = f"Food Audit Replied: {em} ({reason})"
                d = em.split('@')[-1]
                if d not in GENERIC_DOMS:
                    tracker_replied_domains[d] = f"Food Audit Domain: @{d} ({reason})"
            if c_name:
                nc = norm_name(c_name)
                if len(nc) >= 5:
                    tracker_replied_companies[nc] = f"Food Audit Company: '{c_name}' ({reason})"
        print(f"[+] Đã nạp thêm {len(replied_food)} bản ghi phản hồi từ Food Audit.")

    # 3. Nạp danh sách bounce đã phát hiện
    known_bounces = set()
    if POUL_BOUNCE_CSV.exists():
        df_pb = pd.read_csv(POUL_BOUNCE_CSV, encoding='utf-8-sig', dtype=str).fillna('')
        for em in df_pb['Email']:
            em = em.strip().lower()
            if em:
                known_bounces.add(em)
    if FOOD_AUDIT_CSV.exists():
        df_food_audit = pd.read_csv(FOOD_AUDIT_CSV, encoding='utf-8-sig', dtype=str).fillna('')
        bounce_food = df_food_audit[df_food_audit['Lý do loại bỏ'].str.contains('bounce|không dùng được|lỗi', case=False, na=False)]
        for em in bounce_food['Email']:
            em = em.strip().lower()
            if em:
                known_bounces.add(em)
    print(f"[+] Đã nạp {len(known_bounces)} email bounce cần loại trừ.")

    # 4. Đọc dữ liệu LT_POUL_WEBD_2COL.csv
    df = pd.read_csv(TARGET_CSV, encoding='utf-8-sig', dtype=str).fillna('')
    total_initial = len(df)
    initial_with_email = len([1 for _, r in df.iterrows() if r.get('Email', '').strip() and '@' in r.get('Email', '')])
    print(f"[*] Tổng số doanh nghiệp ban đầu: {total_initial:,} (Có Email: {initial_with_email:,})\n")

    # 5. Đối soát chi tiết
    valid_with_email = []
    valid_without_email = []
    removed_records = []

    for idx, r in df.iterrows():
        comp = r.get('Công ty', '').strip()
        c_norm = norm_name(comp)
        em = r.get('Email', '').strip().lower()
        rep = r.get('Trạng thái Reply', '').strip()
        phone = clean_phone(r.get('SĐT', ''))

        row_dict = {col: r.get(col, '') for col in COLUMNS_20}
        row_dict['SĐT'] = phone

        remove_reason = None

        # Tiêu chí 1: Danh sách đen cố định (Hard Blacklist)
        if is_blacklisted(comp):
            remove_reason = f"Hard Blacklist: {comp}"

        # Tiêu chí 2: Trạng thái Reply ghi nhận trong row
        elif 'reply' in rep.lower() or 'phản hồi' in rep.lower():
            remove_reason = f"Đã phản hồi ghi trong file: {rep}"

        # Tiêu chí 3: Trùng Email đã phản hồi trong Mail Tracker / Audit
        elif em and em in tracker_replied_emails:
            remove_reason = f"Email đã phản hồi: {tracker_replied_emails[em]}"

        # Tiêu chí 4: Trùng Corporate Domain đã phản hồi trong Mail Tracker / Audit
        elif em and '@' in em and em.split('@')[-1] in tracker_replied_domains:
            d = em.split('@')[-1]
            remove_reason = f"Domain đã phản hồi: {tracker_replied_domains[d]}"

        # Tiêu chí 5: Trùng tên công ty đã phản hồi
        elif len(c_norm) >= 5:
            for t_comp, t_desc in tracker_replied_companies.items():
                if c_norm == t_comp or (len(c_norm) >= 6 and (c_norm in t_comp or t_comp in c_norm)):
                    remove_reason = f"Tên công ty đã phản hồi: {t_desc}"
                    break

        # Tiêu chí 6: Trùng email bounce đã biết -> Xóa email (không xóa công ty)
        if not remove_reason and em and em in known_bounces:
            print(f"  [XÓA BOUNCE] Row {r.get('No.')}: '{comp}' | Email bounce: '{em}' -> Xóa email")
            row_dict['Email'] = ''
            em = ''

        if remove_reason:
            log_row = dict(row_dict)
            log_row['Lý do loại bỏ'] = remove_reason
            removed_records.append(log_row)
            print(f"  [LOẠI BỎ] Row {r.get('No.')}: '{comp}' | Mail: '{em}' -> {remove_reason}")
        else:
            row_dict['Trạng thái Reply'] = ''
            if em and '@' in em:
                valid_with_email.append(row_dict)
            else:
                row_dict['Check gửi'] = ''
                valid_without_email.append(row_dict)

    print("\n" + "=" * 80)
    print(" KẾT QUẢ ĐỐI SOÁT & LÀM SẠCH")
    print("=" * 80)
    print(f"[*] Doanh nghiệp bị loại bỏ (đã phản hồi / blacklist): {len(removed_records):,}")
    print(f"[*] Doanh nghiệp sạch giữ lại: {len(valid_with_email) + len(valid_without_email):,}")
    print(f"    - Có Email hợp lệ (xếp đầu tệp): {len(valid_with_email):,}")
    print(f"    - Chưa có Email (xếp cuối tệp): {len(valid_without_email):,}")

    # Xuất file audit các bản ghi loại bỏ nếu có
    if removed_records:
        OUT_AUDIT_CSV.parent.mkdir(parents=True, exist_ok=True)
        df_removed = pd.DataFrame(removed_records)
        df_removed.to_csv(OUT_AUDIT_CSV, index=False, encoding='utf-8-sig')
        print(f"[+] Đã lưu log loại bỏ vào: {OUT_AUDIT_CSV}")

    # Gộp danh sách: có Email trước, không Email sau
    final_records = valid_with_email + valid_without_email
    for i, rec in enumerate(final_records, start=1):
        rec['No.'] = str(i)

    df_final = pd.DataFrame(final_records, columns=COLUMNS_20)

    # Lưu và đồng bộ
    df_final.to_csv(TARGET_CSV, index=False, encoding='utf-8-sig')
    print(f"[+] Đã cập nhật tệp chính: {TARGET_CSV} ({len(df_final):,} dòng)")

    CSDL_CSV.parent.mkdir(parents=True, exist_ok=True)
    df_final.to_csv(CSDL_CSV, index=False, encoding='utf-8-sig')
    print(f"[+] Đã đồng bộ sang CSDL: {CSDL_CSV}")

    ARCHIVE_CSV.parent.mkdir(parents=True, exist_ok=True)
    df_final.to_csv(ARCHIVE_CSV, index=False, encoding='utf-8-sig')
    print(f"[+] Đã đồng bộ sang Archive: {ARCHIVE_CSV}")

    print("\n[OK] Hoàn tất đối chiếu và làm sạch 100%!")

if __name__ == '__main__':
    main()

