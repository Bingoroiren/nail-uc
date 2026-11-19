# -*- coding: utf-8 -*-
"""
ĐỐI CHIẾU & LÀM SẠCH LT_WOOD_INLT_2COL.csv VỚI MAIL TRACKER & LT_WOOD_COMB - CleanData.csv
------------------------------------------------------------------------------------------
Mục tiêu:
1. Đối chiếu Mail Tracker (Mail Tracker - mail.csv) và LT_WOOD_COMB - CleanData.csv:
   - Loại bỏ toàn bộ các công ty đã phản hồi (Replied / Phản hồi).
   - Loại bỏ toàn bộ các công ty có mail lỗi / bounce (Email không dùng được).
   - Loại bỏ doanh nghiệp thuộc Hard Blacklist (Scandi Standard, Biliarta, Daigre per GEMINI.md).
2. Tạo bản sao lưu backup an toàn: 'LT_WOOD_INLT_2COL_pre_filter_backup.csv'.
3. Xuất file audit các bản ghi đã loại bỏ: 'archive/lt_lithuania/LT_WOOD_INLT_DA_LOAI_BO_REPLY_BOUNCE.csv'.
4. Chuẩn hóa và làm sạch file đích:
   - Đẩy 100% doanh nghiệp có Email hợp lệ lên đầu tệp (hàng 1..N).
   - Doanh nghiệp chưa có Email xếp ở phần dưới.
   - Đánh lại số thứ tự No. liên tục từ 1 đến hết.
   - SĐT có nháy đơn (') ở đầu theo chuẩn data-standards.
   - UTF-8 with BOM (utf-8-sig) cho toàn bộ file CSV.
5. Đồng bộ vào csdl_mlt/LT_WOOD_INLT_2COL.csv và archive/lt_lithuania/LT_WOOD_INLT_2COL.csv.
6. Đồng bộ xuất tệp LT_WOOD_INLT_ONLY_EMAILS_READY.csv (chỉ các công ty có email sạch).
"""

import sys
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

TARGET_CSV = ROOT_DIR / "LT_WOOD_INLT_2COL.csv"
BACKUP_CSV = ROOT_DIR / "LT_WOOD_INLT_2COL_pre_filter_backup.csv"

FILE_TRACKER = ROOT_DIR / "Mail Tracker - mail.csv"
FILE_CLEANDATA = ROOT_DIR / "LT_WOOD_COMB - CleanData.csv"

OUT_REMOVED_CSV = ROOT_DIR / "archive" / "lt_lithuania" / "LT_WOOD_INLT_DA_LOAI_BO_REPLY_BOUNCE.csv"
OUT_READY_CSV = ROOT_DIR / "LT_WOOD_INLT_ONLY_EMAILS_READY.csv"

SYNC_2COL_CSDL = ROOT_DIR / "csdl_mlt" / "LT_WOOD_INLT_2COL.csv"
SYNC_2COL_ARCHIVE = ROOT_DIR / "archive" / "lt_lithuania" / "LT_WOOD_INLT_2COL.csv"

SYNC_READY_CSDL = ROOT_DIR / "csdl_mlt" / "LT_WOOD_INLT_ONLY_EMAILS_READY.csv"
SYNC_READY_ARCHIVE = ROOT_DIR / "archive" / "lt_lithuania" / "LT_WOOD_INLT_ONLY_EMAILS_READY.csv"

COLUMNS_20 = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

GENERIC_DOMS = {
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
    'centrum.sk', 'centrum.cz', 'zoznam.sk', 'post.sk', 'azet.sk', 'seznam.cz',
    'inbox.lt', 'inbox.lv', 'mail.ru', 'yandex.ru', 'email.cz'
}

PERMANENT_BLACKLIST = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre'
]

def clean_phone(p):
    if not p or str(p).strip() == '' or str(p) == 'nan':
        return ''
    s = str(p).strip()
    return f"'{s}" if not s.startswith("'") else s

def clean_email_str(em):
    if not em:
        return ""
    e = str(em).strip().lower()
    e = re.sub(r'^(mailto:|u003e|20)', '', e, flags=re.I).strip()
    return e

def norm_name(name):
    if not name:
        return ""
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    for legal in ['uzdaroji akcine bendrove', 'mazoji bendrija', 'akcine bendrove', 'viesoji istaiga',
                  'uab', 'mb', 'vsi', 'ab', 'ii', 's.r.o.', 'a.s.', 'gmbh']:
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
    print(" 🚀 ĐỐI CHIẾU & LÀM SẠCH LT_WOOD_INLT_2COL.csv")
    print("    Nguồn đối soát: Mail Tracker - mail.csv & LT_WOOD_COMB - CleanData.csv")
    print("    Mục tiêu: Xoá triệt để Email lỗi / Bounced & Doanh nghiệp đã Reply")
    print("=" * 80)

    if not TARGET_CSV.exists():
        print(f"[-] Không tìm thấy tệp mục tiêu: {TARGET_CSV}")
        return

    # 1. Nạp Mail Tracker
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
                    tracker_emails[em] = f"Tracker ({desc})"
                    d = em.split('@')[-1]
                    if d not in GENERIC_DOMS:
                        tracker_domains[d] = f"Tracker Domain @{d} ({desc})"

            for txt in [note, subj]:
                n_comp = norm_name(txt)
                if len(n_comp) >= 5 and not any(k in n_comp for k in ['re asian', 're labor', 're reliable', 'fwd', 're personnel', 're nail']):
                    tracker_companies[n_comp] = f"Tracker Company '{txt[:30]}' ({desc})"

        print(f"[+] Đã nạp từ Mail Tracker: {len(tracker_emails):,} emails & {len(tracker_domains):,} corporate domains.")
    else:
        print(f"[!] Không tìm thấy file: {FILE_TRACKER}")

    # 2. Nạp CleanData
    cleandata_issue_emails = {}
    cleandata_issue_comps = {}

    if FILE_CLEANDATA.exists():
        df_comb = pd.read_csv(FILE_CLEANDATA, encoding='utf-8-sig', dtype=str).fillna('')
        for idx, r in df_comb.iterrows():
            rep = r.get('Trạng thái Reply', '').strip()
            if rep:
                em = clean_email_str(r.get('Email', ''))
                comp = r.get('Công ty', '').strip()
                c_norm = norm_name(comp)
                
                reason = f"CleanData ({rep})"
                if em:
                    cleandata_issue_emails[em] = reason
                if c_norm and len(c_norm) >= 4:
                    cleandata_issue_comps[c_norm] = reason
        print(f"[+] Đã nạp từ CleanData: {len(cleandata_issue_emails)} email phản hồi / lỗi bounce.")
    else:
        print(f"[!] Không tìm thấy file: {FILE_CLEANDATA}")

    # 3. Tạo bản sao lưu backup an toàn
    shutil.copy2(TARGET_CSV, BACKUP_CSV)
    print(f"[+] Đã tạo backup an toàn tại: {BACKUP_CSV.name}")

    # 4. Đọc dữ liệu LT_WOOD_INLT_2COL.csv
    df = pd.read_csv(TARGET_CSV, encoding='utf-8-sig', dtype=str).fillna('')
    total_initial = len(df)
    initial_with_email = len([1 for _, r in df.iterrows() if r.get('Email', '').strip() and '@' in r.get('Email', '')])
    print(f"[*] Tổng số doanh nghiệp ban đầu: {total_initial:,} (Trong đó có Email: {initial_with_email:,})\n")

    # 5. Phân loại và lọc bỏ
    valid_with_email = []
    valid_without_email = []
    removed_records = []

    for idx, r in df.iterrows():
        comp = r.get('Công ty', '').strip()
        c_norm = norm_name(comp)
        raw_em = r.get('Email', '').strip()
        em = clean_email_str(raw_em)
        phone = clean_phone(r.get('SĐT', ''))

        row_dict = {col: r.get(col, '') for col in COLUMNS_20}
        row_dict['SĐT'] = phone
        row_dict['Email'] = em
        row_dict['Liên Hệ mail'] = f"mailto:{em}" if em else ""

        remove_reason = None

        # Tiêu chí 1: Danh sách đen cố định (Hard Blacklist)
        if is_blacklisted(comp):
            remove_reason = f"Danh sách đen vĩnh viễn (Hard Blacklist): {comp}"

        # Tiêu chí 2: Email lỗi/reply từ CleanData
        elif em and em in cleandata_issue_emails:
            remove_reason = f"CleanData: {cleandata_issue_emails[em]}"

        # Tiêu chí 3: Tên công ty lỗi/reply từ CleanData
        elif c_norm and c_norm in cleandata_issue_comps:
            remove_reason = f"CleanData: {cleandata_issue_comps[c_norm]}"

        # Tiêu chí 4: Trùng Email trong Mail Tracker
        elif em and em in tracker_emails:
            remove_reason = f"Trùng Email trong Mail Tracker: {tracker_emails[em]}"

        # Tiêu chí 5: Trùng Corporate Domain trong Mail Tracker
        elif em and '@' in em and em.split('@')[-1] in tracker_domains:
            d = em.split('@')[-1]
            remove_reason = f"Trùng Corporate Domain trong Mail Tracker: {tracker_domains[d]}"

        # Tiêu chí 6: Trùng tên công ty ghi nhận đối soát trong Mail Tracker
        elif len(c_norm) >= 5:
            for t_comp, t_desc in tracker_companies.items():
                if c_norm == t_comp or (len(c_norm) >= 6 and (c_norm in t_comp or t_comp in c_norm)):
                    remove_reason = f"Trùng tên công ty trong Mail Tracker: {t_desc}"
                    break

        if remove_reason:
            log_row = dict(row_dict)
            log_row['Lý do loại bỏ'] = remove_reason
            removed_records.append(log_row)
            print(f"  ❌ [XÓA] Row {r.get('No.')}: '{comp[:30]}' | Mail: '{raw_em}' -> {remove_reason}")
        else:
            row_dict['Trạng thái Reply'] = ''
            if em and '@' in em:
                valid_with_email.append(row_dict)
            else:
                row_dict['Check gửi'] = ''
                valid_without_email.append(row_dict)

    print("\n" + "=" * 80)
    print(" 📊 KẾT QUẢ ĐỐI SOÁT & LÀM SẠCH")
    print("=" * 80)
    count_reply = sum(1 for x in removed_records if any(k in x['Lý do loại bỏ'].lower() for k in ['đã reply', 'đã phản hồi', 'phản hồi']))
    count_bounce = sum(1 for x in removed_records if any(k in x['Lý do loại bỏ'].lower() for k in ['bounce', 'không dùng được', 'lỗi']) and not any(k in x['Lý do loại bỏ'].lower() for k in ['đã reply', 'đã phản hồi']))
    count_blacklist = sum(1 for x in removed_records if 'blacklist' in x['Lý do loại bỏ'].lower())

    print(f"[*] Tổng số doanh nghiệp ban đầu  : {total_initial:,}")
    print(f"[*] Số doanh nghiệp bị loại bỏ     : {len(removed_records):,}")
    print(f"    - Doanh nghiệp đã Reply       : {count_reply:,}")
    print(f"    - Mail lỗi / Bounced          : {count_bounce:,}")
    print(f"    - Hard Blacklist              : {count_blacklist:,}")
    print(f"[*] Số doanh nghiệp sạch giữ lại   : {len(valid_with_email) + len(valid_without_email):,}")
    print(f"    - Có Email hợp lệ (xếp đầu)   : {len(valid_with_email):,}")
    print(f"    - Chưa có Email (xếp dưới)    : {len(valid_without_email):,}")
    print("=" * 80)

    # 6. Sắp xếp lại No. từ 1 đến hết (100% dòng có email lên hàng 1..N)
    all_clean = valid_with_email + valid_without_email
    for i, r in enumerate(all_clean, 1):
        r['No.'] = str(i)

    df_clean = pd.DataFrame(all_clean, columns=COLUMNS_20)

    # 7. Lưu file đích chính LT_WOOD_INLT_2COL.csv
    df_clean.to_csv(TARGET_CSV, index=False, encoding='utf-8-sig')
    print(f"[✓] Đã cập nhật file chính: {TARGET_CSV.name} ({len(df_clean):,} dòng, {len(valid_with_email):,} dòng có email)")

    # 8. Đồng bộ sang csdl_mlt và archive
    if SYNC_2COL_CSDL.parent.exists():
        df_clean.to_csv(SYNC_2COL_CSDL, index=False, encoding='utf-8-sig')
        print(f"[✓] Đã đồng bộ sang: {SYNC_2COL_CSDL}")
    if SYNC_2COL_ARCHIVE.parent.exists():
        df_clean.to_csv(SYNC_2COL_ARCHIVE, index=False, encoding='utf-8-sig')
        print(f"[✓] Đã đồng bộ sang: {SYNC_2COL_ARCHIVE}")

    # 9. Xuất tệp LT_WOOD_INLT_ONLY_EMAILS_READY.csv (chỉ gồm các công ty có email)
    for i, r in enumerate(valid_with_email, 1):
        r['No.'] = str(i)
    df_ready = pd.DataFrame(valid_with_email, columns=COLUMNS_20)
    df_ready.to_csv(OUT_READY_CSV, index=False, encoding='utf-8-sig')
    print(f"[✓] Đã cập nhật file READY: {OUT_READY_CSV.name} ({len(df_ready):,} công ty sẵn sàng gửi)")

    if SYNC_READY_CSDL.parent.exists():
        df_ready.to_csv(SYNC_READY_CSDL, index=False, encoding='utf-8-sig')
        print(f"[✓] Đã đồng bộ READY sang: {SYNC_READY_CSDL}")
    if SYNC_READY_ARCHIVE.parent.exists():
        df_ready.to_csv(SYNC_READY_ARCHIVE, index=False, encoding='utf-8-sig')
        print(f"[✓] Đã đồng bộ READY sang: {SYNC_READY_ARCHIVE}")

    # 10. Xuất file Audit các bản ghi bị loại bỏ
    if removed_records:
        OUT_REMOVED_CSV.parent.mkdir(parents=True, exist_ok=True)
        cols_log = COLUMNS_20 + ['Lý do loại bỏ']
        df_removed = pd.DataFrame(removed_records, columns=cols_log)
        df_removed.to_csv(OUT_REMOVED_CSV, index=False, encoding='utf-8-sig')
        print(f"[✓] Đã lưu tệp audit loại bỏ tại: {OUT_REMOVED_CSV.name} ({len(removed_records)} bản ghi)")

    print("\n🎉 HOÀN THÀNH LÀM SẠCH VÀ ĐỐI SOÁT TRỌN VẸN!")

if __name__ == "__main__":
    main()
