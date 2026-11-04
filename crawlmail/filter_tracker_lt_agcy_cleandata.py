# -*- coding: utf-8 -*-
"""
ĐỐI CHIẾU & LÀM SẠCH (xong 10_24) LT_AGCY_REKV - CleanData.csv VỚI MAIL TRACKER
-----------------------------------------------------------------------------------
Mục tiêu:
1. Đối chiếu Mail Tracker (Mail Tracker - mail.csv) và cột 'Trạng thái Reply' trong file:
   - Loại bỏ toàn bộ các công ty đã phản hồi (Replied / Phản hồi).
   - Loại bỏ toàn bộ các công ty có mail lỗi / bounce (Email không dùng được).
   - Loại bỏ doanh nghiệp thuộc Hard Blacklist (Scandi Standard, Biliarta, Daigre per GEMINI.md).
2. Tạo bản sao lưu backup an toàn: '(xong 10_24) LT_AGCY_REKV - CleanData_pre_filter_backup.csv'.
3. Xuất file audit các bản ghi đã loại bỏ: 'archive/lt_lithuania/LT_AGCY_DA_LOAI_BO_REPLY_BOUNCE.csv'.
4. Chuẩn hóa và làm sạch file đích:
   - Đẩy 100% doanh nghiệp có Email hợp lệ lên đầu tệp.
   - Doanh nghiệp chưa có Email xếp ở phần dưới.
   - Đánh lại số thứ tự No. liên tục từ 1 đến hết.
   - SĐT có nháy đơn (') ở đầu theo chuẩn data-standards.
   - UTF-8 with BOM (utf-8-sig) cho toàn bộ file CSV.
5. Đồng bộ vào LT_AGCY_REKV_2COL.csv và csdl_mlt/LT_AGCY_REKV_2COL.csv nếu tồn tại.
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

TARGET_CSV = ROOT_DIR / "(xong 10_24) LT_AGCY_REKV - CleanData.csv"
BACKUP_CSV = ROOT_DIR / "(xong 10_24) LT_AGCY_REKV - CleanData_pre_filter_backup.csv"

FILE_TRACKER = ROOT_DIR / "Mail Tracker - mail.csv"
OUT_REMOVED_CSV = ROOT_DIR / "archive" / "lt_lithuania" / "LT_AGCY_DA_LOAI_BO_REPLY_BOUNCE.csv"
ROOT_2COL_CSV = ROOT_DIR / "LT_AGCY_REKV_2COL.csv"
CSDL_2COL_CSV = ROOT_DIR / "csdl_mlt" / "LT_AGCY_REKV_2COL.csv"

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
    print(" ĐỐI CHIẾU & LÀM SẠCH (xong 10_24) LT_AGCY_REKV - CleanData.csv")
    print(" LOẠI BỎ EMAIL BOUNCE, EMAIL ĐÃ PHẢN HỒI & ĐỐI SOÁT MAIL TRACKER")
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
                    tracker_emails[em] = f"Tracker Email: {em} ({desc})"
                    d = em.split('@')[-1]
                    if d not in GENERIC_DOMS:
                        tracker_domains[d] = f"Tracker Domain: @{d} ({desc})"

            for txt in [note, subj]:
                n_comp = norm_name(txt)
                if len(n_comp) >= 5 and not any(k in n_comp for k in ['re asian', 're labor', 're reliable', 'fwd', 're personnel', 're nail']):
                    tracker_companies[n_comp] = f"Tracker Company: '{txt[:30]}' ({desc})"

        print(f"[+] Đã nạp từ Mail Tracker: {len(tracker_emails):,} emails & {len(tracker_domains):,} corporate domains.")
    else:
        print(f"[!] Không tìm thấy file: {FILE_TRACKER}")

    # 2. Tạo bản sao lưu backup an toàn
    shutil.copy2(TARGET_CSV, BACKUP_CSV)
    print(f"[+] Đã tạo backup an toàn tại: {BACKUP_CSV.name}")

    # 3. Đọc dữ liệu CleanData
    df = pd.read_csv(TARGET_CSV, encoding='utf-8-sig', dtype=str).fillna('')
    total_initial = len(df)
    initial_with_email = len([1 for _, r in df.iterrows() if r.get('Email', '').strip() and '@' in r.get('Email', '')])
    print(f"[*] Tổng số doanh nghiệp ban đầu: {total_initial:,} (Trong đó có Email: {initial_with_email:,})\n")

    # 4. Phân loại và lọc bỏ
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
            remove_reason = f"Danh sách đen vĩnh viễn (Hard Blacklist): {comp}"

        # Tiêu chí 2: Đã phản hồi (Replied) ghi nhận trong file
        elif 'reply' in rep.lower() or 'phản hồi' in rep.lower():
            remove_reason = f"Đã phản hồi trong CleanData: {rep}"

        # Tiêu chí 3: Mail lỗi / Bounce ghi nhận trong file
        elif any(k in rep.lower() for k in ['bounce', 'không dùng được', 'khong dung duoc', 'lỗi', 'loi']):
            remove_reason = f"Mail lỗi / Bounce trong CleanData: {rep}"

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
            print(f"  [XÓA] Row {r.get('No.')}: '{comp}' | Mail: '{em}' -> {remove_reason}")
        else:
            # Dọn sạch Trạng thái Reply cho các dòng sạch giữ lại
            row_dict['Trạng thái Reply'] = ''
            if em and '@' in em:
                valid_with_email.append(row_dict)
            else:
                row_dict['Check gửi'] = ''
                valid_without_email.append(row_dict)

    print("\n" + "=" * 80)
    print(" KẾT QUẢ ĐỐI SOÁT & LÀM SẠCH")
    print("=" * 80)
    print(f"[*] Tổng số doanh nghiệp ban đầu  : {total_initial:,}")
    print(f"[*] Số doanh nghiệp bị loại bỏ     : {len(removed_records):,}")
    print(f"    - Doanh nghiệp đã Reply       : {sum(1 for x in removed_records if 'reply' in x['Lý do loại bỏ'].lower() or 'phản hồi' in x['Lý do loại bỏ'].lower()):,}")
    print(f"    - Mail lỗi / Bounced          : {sum(1 for x in removed_records if 'bounce' in x['Lý do loại bỏ'].lower() or 'lỗi' in x['Lý do loại bỏ'].lower()):,}")
    print(f"    - Hard Blacklist              : {sum(1 for x in removed_records if 'blacklist' in x['Lý do loại bỏ'].lower()):,}")
    print(f"[*] Số doanh nghiệp sạch giữ lại   : {len(valid_with_email) + len(valid_without_email):,}")
    print(f"    - Có Email hợp lệ (xếp đầu)   : {len(valid_with_email):,}")
    print(f"    - Chưa có Email (xếp dưới)    : {len(valid_without_email):,}")

    # 5. Đánh số lại No. liên tục & Ghép danh sách
    final_rows = []
    current_no = 1
    for row in valid_with_email:
        row['No.'] = str(current_no)
        final_rows.append(row)
        current_no += 1

    for row in valid_without_email:
        row['No.'] = str(current_no)
        final_rows.append(row)
        current_no += 1

    # 6. Ghi đè vào file CleanData chính
    df_final = pd.DataFrame(final_rows, columns=COLUMNS_20)
    df_final.to_csv(TARGET_CSV, index=False, encoding='utf-8-sig')
    print(f"\n[✔] Đã cập nhật tệp mục tiêu: {TARGET_CSV.name} ({len(df_final):,} dòng)")

    # 7. Đồng bộ ra root và csdl_mlt nếu có
    if ROOT_2COL_CSV.exists():
        df_final.to_csv(ROOT_2COL_CSV, index=False, encoding='utf-8-sig')
        print(f"[✔] Đã đồng bộ sang: {ROOT_2COL_CSV.name}")
    if CSDL_2COL_CSV.parent.exists():
        df_final.to_csv(CSDL_2COL_CSV, index=False, encoding='utf-8-sig')
        print(f"[✔] Đã đồng bộ sang: {CSDL_2COL_CSV}")

    # 8. Xuất file Audit các bản ghi bị loại bỏ
    if removed_records:
        OUT_REMOVED_CSV.parent.mkdir(parents=True, exist_ok=True)
        audit_cols = list(COLUMNS_20) + ['Lý do loại bỏ']
        df_removed = pd.DataFrame(removed_records, columns=audit_cols)
        df_removed.to_csv(OUT_REMOVED_CSV, index=False, encoding='utf-8-sig')
        print(f"[✔] Đã lưu danh sách loại bỏ vào: {OUT_REMOVED_CSV.name} ({len(df_removed):,} dòng)")

    print("\n" + "=" * 80)
    print(f" HOÀN TẤT LÀM SẠCH DỮ LIỆU LT_AGCY THÀNH CÔNG!")
    print(f" [*] Đẩy 100% doanh nghiệp có Email sạch ({len(valid_with_email):,} cty) từ No. 1 đến No. {len(valid_with_email):,}")
    print(f" [*] SĐT có nháy đơn ', mã hóa UTF-8-sig đúng chuẩn.")
    print("=" * 80 + "\n")

if __name__ == '__main__':
    main()

