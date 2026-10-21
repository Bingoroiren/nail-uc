# -*- coding: utf-8 -*-
"""
Cross-reference and enrich AT_AGCY_COMB_2COL.csv with AT_AGCY_WKOS - CleanData.csv:
1. Doi chieu thong minh (Smart & Strict Match: Exact, Token Set, Phone, Email).
2. XOA BO 100% cac cong ty da REPLY (Trang thai Reply co chua 'reply') de khong gui mail lai.
3. Loc bo cac email da bi BOUNCE (khong dung duoc).
4. Lam giau (Enrich) Email, So dien thoai (luon co dau nhay don '), Dia chi cho cac cong ty con thieu.
5. Luon day 100% cong ty Co Email len dau danh sach CSV.
6. Xuat file:
   - AT_AGCY_COMB_2COL.csv (cap nhat truc tiep)
   - data/AT_AGCY_COMB_2COL.csv (dong bo luu kho)
   - AT_AGCY_GMAP_2COL.csv (chuan dat ten 17 ky tu [CC]_[IND4]_[SRC4]_[STG4].csv)
   - data/AT_AGCY_REPLIED_REMOVED.csv (danh sach cong ty da reply duoc loai bo de doi chieu)
"""

import sys
import os
import re
import csv
import time
import unicodedata
from datetime import datetime
from pathlib import Path

# Cau hinh UTF-8 cho console Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

MAIN_CSV = str(ROOT_DIR / "AT_AGCY_COMB_2COL.csv")
DATA_DIR_CSV = str(ROOT_DIR / "data" / "AT_AGCY_COMB_2COL.csv")
CLEANDATA_CSV = str(ROOT_DIR / "AT_AGCY_WKOS - CleanData.csv")
OUTPUT_17CHAR = str(ROOT_DIR / "AT_AGCY_GMAP_2COL.csv")
REPLIED_LOG_CSV = str(ROOT_DIR / "data" / "AT_AGCY_REPLIED_REMOVED.csv")

from crawlmail.enrich_maps_at_agcy import (
    clean_company_name_at,
    is_valid_name_match_at,
    score_email_b2b
)

def extract_phone_key(phone_str):
    if not phone_str:
        return ""
    digits = re.sub(r'\D', '', str(phone_str))
    return digits[-8:] if len(digits) >= 8 else digits

def main():
    if not os.path.exists(MAIN_CSV):
        print(f"[-] Khong tim thay file chinh: {MAIN_CSV}")
        return
    if not os.path.exists(CLEANDATA_CSV):
        print(f"[-] Khong tim thay file doi chieu: {CLEANDATA_CSV}")
        return

    print("=" * 80)
    print("🚀 BẮT ĐẦU ĐỐI CHIẾU & LÀM GIÀU DỮ LIỆU AGENCY ÁO VỚI WKO CLEANDATA")
    print(f"📂 File nguồn chính    : {MAIN_CSV}")
    print(f"📂 File đối chiếu       : {CLEANDATA_CSV}")
    print("=" * 80)

    # 1. Đọc CleanData
    with open(CLEANDATA_CSV, 'r', encoding='utf-8-sig', errors='ignore') as f:
        clean_reader = csv.DictReader(f)
        clean_rows = list(clean_reader)

    print(f"[*] Đã nạp {len(clean_rows)} bản ghi từ AT_AGCY_WKOS - CleanData.csv")

    replied_list = []
    bounced_emails = set()
    clean_norm_lookup = {}
    clean_token_lookup = {}
    clean_phone_lookup = {}
    clean_email_lookup = {}

    for r in clean_rows:
        c_name = r.get('Công ty', '').strip()
        c_email = r.get('Email', '').strip().lower()
        c_phone = r.get('SĐT', '').strip()
        c_phone_key = extract_phone_key(c_phone)
        st_reply = r.get('Trạng thái Reply', '').strip()

        c_norm = clean_company_name_at(c_name)
        c_tokens = tuple(sorted(set(t for t in c_norm.split() if len(t) > 2)))

        # Nhận diện công ty đã reply
        if 'reply' in st_reply.lower():
            replied_list.append({
                'name': c_name,
                'norm': c_norm,
                'tokens': c_tokens,
                'email': c_email,
                'phone_key': c_phone_key,
                'status': st_reply
            })

        # Nhận diện email đã bounce
        if 'bounce' in st_reply.lower() and c_email:
            bounced_emails.add(c_email)

        # Xây dựng bảng tra cứu
        if c_norm and c_norm not in clean_norm_lookup:
            clean_norm_lookup[c_norm] = r
        if len(c_tokens) >= 2 and c_tokens not in clean_token_lookup:
            clean_token_lookup[c_tokens] = r
        if c_phone_key and len(c_phone_key) >= 7 and c_phone_key not in clean_phone_lookup:
            clean_phone_lookup[c_phone_key] = r
        if c_email and c_email not in clean_email_lookup:
            clean_email_lookup[c_email] = r

    print(f"[*] Số công ty ĐÃ REPLY cần loại bỏ : {len(replied_list)}")
    print(f"[*] Số email BOUNCE cần tránh       : {len(bounced_emails)}")

    # 2. Đọc Main CSV
    with open(MAIN_CSV, 'r', encoding='utf-8-sig', errors='ignore') as f:
        main_reader = csv.DictReader(f)
        fieldnames = list(main_reader.fieldnames)
        comb_rows = list(main_reader)

    initial_total = len(comb_rows)
    initial_with_email = len([r for r in comb_rows if r.get('Email', '').strip()])
    print(f"[*] Tổng số công ty trong file hiện tại: {initial_total} (Đã có email: {initial_with_email})")

    # 3. Quá trình kiểm tra Replied và Làm giàu
    active_rows = []
    removed_replied_rows = []

    enriched_emails_count = 0
    enriched_phones_count = 0
    bounced_cleared_count = 0

    for idx, r in enumerate(comb_rows):
        company = r.get('Company', '').strip()
        email = r.get('Email', '').strip().lower()
        phone = r.get('Phone', '').strip()
        phone_key = extract_phone_key(phone)
        norm_name = clean_company_name_at(company)
        tokens = tuple(sorted(set(t for t in norm_name.split() if len(t) > 2)))

        # BƯỚC A: KIỂM TRA ĐÃ REPLY
        is_replied = False
        rep_reason = ""

        for rep in replied_list:
            # 1. Trùng email
            if email and rep['email'] and email == rep['email']:
                is_replied = True
                rep_reason = f"Trùng Email ({email}) -> {rep['status']}"
                break
            # 2. Trùng SĐT
            if phone_key and rep['phone_key'] and phone_key == rep['phone_key']:
                is_replied = True
                rep_reason = f"Trùng SĐT ({phone}) -> {rep['status']}"
                break
            # 3. Trùng tên chuẩn hoá
            if norm_name and rep['norm'] and norm_name == rep['norm']:
                is_replied = True
                rep_reason = f"Trùng tên ({company} == {rep['name']}) -> {rep['status']}"
                break
            # 4. Trùng token đảo tên (Họ Tên vs Tên Họ)
            if len(tokens) >= 2 and len(rep['tokens']) >= 2 and tokens == rep['tokens']:
                is_replied = True
                rep_reason = f"Trùng đảo tên ({company} ~ {rep['name']}) -> {rep['status']}"
                break
            # 5. So khớp nghiêm ngặt
            matched, mtype = is_valid_name_match_at(company, rep['name'])
            if matched:
                is_replied = True
                rep_reason = f"So khớp thông minh ({company} ~ {rep['name']} [{mtype}]) -> {rep['status']}"
                break

        if is_replied:
            removed_r = dict(r)
            removed_r['Removed_Reason'] = rep_reason
            removed_replied_rows.append(removed_r)
            print(f"  ❌ [XÓA ĐÃ REPLY] {company} | {email or 'Không mail'} | {rep_reason}")
            continue

        # BƯỚC B: LÀM SẠCH EMAIL BOUNCE
        if email and email in bounced_emails:
            print(f"  ⚠️ [XOÁ BOUNCE] {company}: Email {email} từng bị bounce -> Huỷ bỏ email này")
            r['Email'] = ''
            r['Custom_Note'] = (r.get('Custom_Note', '') + ' | Email cu tung bi bounce').strip(' |')
            email = ''
            bounced_cleared_count += 1

        # BƯỚC C: LÀM GIÀU DỮ LIỆU TỪ CLEANDATA
        match_clean = None

        # 1. Tra cứu theo tên chuẩn hoá
        if norm_name in clean_norm_lookup:
            match_clean = clean_norm_lookup[norm_name]
        # 2. Tra cứu theo token đảo tên
        elif len(tokens) >= 2 and tokens in clean_token_lookup:
            match_clean = clean_token_lookup[tokens]
        # 3. Tra cứu theo SĐT
        elif phone_key and phone_key in clean_phone_lookup:
            match_clean = clean_phone_lookup[phone_key]

        if match_clean:
            clean_email = match_clean.get('Email', '').strip()
            clean_phone = match_clean.get('SĐT', '').strip()
            clean_addr = match_clean.get('Địa chỉ', '').strip()

            # Bổ sung Email nếu đang thiếu và email không bị bounce
            if not r.get('Email', '').strip() and clean_email:
                if clean_email.lower() not in bounced_emails:
                    r['Email'] = clean_email
                    r['Lead_Score'] = str(score_email_b2b(clean_email, r.get('Website', '')))
                    r['Verified_Date'] = datetime.now().strftime("%Y-%m")
                    r['Source'] = (r.get('Source', '') + ' + WKO CleanData').strip(' +')
                    enriched_emails_count += 1
                    print(f"  ✨ [BỔ SUNG EMAIL] {company} ➜ {clean_email}")

            # Bổ sung SĐT nếu đang thiếu
            if not r.get('Phone', '').strip() and clean_phone:
                p = f"'{clean_phone}" if not clean_phone.startswith("'") else clean_phone
                r['Phone'] = p
                enriched_phones_count += 1

            # Bổ sung Địa chỉ nếu đang thiếu
            if not r.get('Address', '').strip() and clean_addr:
                r['Address'] = clean_addr

        # Chuẩn hóa dấu nháy đơn cho SĐT
        p_final = r.get('Phone', '').strip()
        if p_final and not p_final.startswith("'"):
            r['Phone'] = f"'{p_final}"

        active_rows.append(r)

    # 4. Lưu danh sách công ty đã bị xoá do Reply
    if removed_replied_rows:
        os.makedirs(os.path.dirname(REPLIED_LOG_CSV), exist_ok=True)
        rep_fieldnames = fieldnames + ['Removed_Reason']
        with open(REPLIED_LOG_CSV, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=rep_fieldnames)
            w.writeheader()
            w.writerows(removed_replied_rows)
        print(f"\n💾 Đã lưu danh sách công ty đã reply vào: {REPLIED_LOG_CSV}")

    # 5. Sắp xếp ưu tiên: 100% CÔNG TY CÓ EMAIL LÊN ĐẦU
    with_email = [r for r in active_rows if r.get('Email', '').strip()]
    without_email = [r for r in active_rows if not r.get('Email', '').strip()]
    sorted_active_rows = with_email + without_email

    final_total = len(sorted_active_rows)
    final_with_email = len(with_email)

    # 6. Ghi đồng bộ ra các file đích
    for target_path in [MAIN_CSV, DATA_DIR_CSV, OUTPUT_17CHAR]:
        out_dir = os.path.dirname(os.path.abspath(target_path))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        temp = target_path + ".tmp"
        with open(temp, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(sorted_active_rows)
        if os.path.exists(target_path):
            try:
                os.remove(target_path)
            except Exception:
                pass
        os.rename(temp, target_path)

    print("\n" + "=" * 80)
    print("🎉 HOÀN TẤT ĐỐI CHIẾU & LÀM GIÀU DỮ LIỆU AGENCY ÁO!")
    print(f"📊 Tổng số công ty ban đầu         : {initial_total}")
    print(f"🗑️ Số công ty ĐÃ REPLY ĐÃ BỊ XÓA   : {len(removed_replied_rows)}")
    print(f"🛡️ Số email Bounce đã được dọn sạch: {bounced_cleared_count}")
    print(f"✉️ Số EMAIL MỚI ĐƯỢC BỔ SUNG       : +{enriched_emails_count}")
    print(f"📞 Số SĐT mới được bổ sung         : +{enriched_phones_count}")
    print(f"📈 TỔNG CÔNG TY CÓ EMAIL HIỆN CÓ    : {final_with_email} (Tăng từ {initial_with_email})")
    print(f"📋 Tổng số công ty còn lại         : {final_total}")
    print(f"💾 File kết quả chính              : {MAIN_CSV}")
    print(f"💾 File chuẩn 17 ký tự             : {OUTPUT_17CHAR}")
    print("=" * 80)

if __name__ == "__main__":
    main()
