# -*- coding: utf-8 -*-
"""
Hợp nhất dữ liệu Hiệp hội KNESA (404 công ty có SĐT di động 010- và địa chỉ chi tiết)
vào danh sách môi giới đóng tàu KR_AGCY_SHIP_0RAW.csv.
Xuất tệp:
- KR_AGCY_SHIP_1ENR.csv
- KR_AGCY_SHIP_2COL.csv (Chuẩn Cold Mail 20 cột, đẩy email/SĐT lên đầu)
"""

import sys
import os
import re
import csv
import json
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
ROOT_DIR = Path(__file__).resolve().parent.parent

RAW_CSV = str(ROOT_DIR / "KR_AGCY_SHIP_0RAW.csv")
KNESA_CSV = str(ROOT_DIR / "crawlmail" / "knesa_ship_agencies_raw.csv")
OUTPUT_1ENR = str(ROOT_DIR / "KR_AGCY_SHIP_1ENR.csv")
OUTPUT_2COL = str(ROOT_DIR / "KR_AGCY_SHIP_2COL.csv")
FMT_2COL = str(ROOT_DIR / "data" / "formatted" / "KR_AGCY_SHIP_2COL.csv")

COLDMAIL_FIELDNAMES = [
    "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ",
    "Email", "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển",
    "Check gửi", "Last Subject", "Last Body HTML", "Trạng thái Reply",
    "Lần Follow-up", "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category"
]

def clean_phone_val(p):
    if not p:
        return ""
    p = p.strip()
    return f"'{p}" if not p.startswith("'") else p

def main():
    print("=" * 80)
    print("HỢP NHẤT DỮ LIỆU KNESA VÀO DANH SÁCH MÔI GIỚI ĐÓNG TÀU HÀN QUỐC")
    print("=" * 80)

    # 1. Đọc tệp KNESA
    knesa_by_name = {}
    knesa_by_ceo = {}
    knesa_all = []

    if os.path.exists(KNESA_CSV):
        with open(KNESA_CSV, encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                cname = re.sub(r'[\(（].*?[\)）]', '', r['company']).strip()
                ceo = r['ceo'].strip()
                knesa_by_name[cname] = r
                if ceo:
                    knesa_by_ceo[ceo] = r
                knesa_all.append(r)
        print(f"[*] Đã nạp {len(knesa_all)} hội viên KNESA có SĐT di động và địa chỉ chi tiết.")

    CKPT_JSON = str(ROOT_DIR / "crawlmail" / "checkpoint_kr_agcy_ship.json")
    ckpt_data = {}
    if os.path.exists(CKPT_JSON):
        try:
            with open(CKPT_JSON, encoding='utf-8') as f:
                ckpt_data = json.load(f)
            print(f"[*] Đã nạp checkpoint: {len(ckpt_data)} bản ghi đã làm giàu online.")
        except Exception:
            pass

    # 2. Đọc tệp MOEL 725 công ty
    with open(RAW_CSV, encoding='utf-8-sig') as f:
        moel_rows = list(csv.DictReader(f))

    enriched_list = []
    matched_knesa_count = 0
    matched_knesa_set = set()

    for idx, r in enumerate(moel_rows, 1):
        cname = r.get('Tên công ty (사업장명)', '').strip()
        if '변경' in cname or len(cname) < 2:
            continue
        ceo = r.get('Người đại diện (대표자)', '').strip()
        loc = r.get('Địa chỉ khu vực (소재지)', '').strip()
        hub = r.get('Cụm xưởng tàu mục tiêu', '').strip()
        # Đọc thêm từ checkpoint nếu có
        clean_cname = re.sub(r'[\(（].*?[\)）]', '', cname).strip()
        key_tuple = f"{cname}_{ceo}_{loc}"
        ckpt_item = ckpt_data.get(key_tuple) or ckpt_data.get(f"{cname}_{ceo}") or ckpt_data.get(cname) or {}

        # Đối chiếu KNESA
        k_match = knesa_by_name.get(clean_cname) or (knesa_by_ceo.get(ceo) if ceo else None)

        phone = ""
        address = loc
        website = ""
        email = ""
        category = f"Môi giới nhân lực - {hub}"

        if ckpt_item:
            if ckpt_item.get('phone'): phone = ckpt_item['phone']
            if ckpt_item.get('address') and len(ckpt_item['address']) > len(address): address = ckpt_item['address']
            if ckpt_item.get('website'): website = ckpt_item['website']
            if ckpt_item.get('email'): email = ckpt_item['email']

        if k_match:
            matched_knesa_count += 1
            matched_knesa_set.add(k_match['company'])
            # KNESA có SĐT di động trực tiếp 010 của giám đốc -> Ưu tiên cao nhất
            if k_match.get('mobile'):
                phone = k_match['mobile']
            elif k_match.get('tel') and not phone:
                phone = k_match['tel']
            if k_match.get('address') and len(k_match['address']) > len(address):
                address = k_match['address']
            if k_match.get('category'):
                category += f" | {k_match['category']}"

        item = {
            'No.': '',
            'Công ty': cname,
            'Chức danh': 'Đại diện pháp luật',
            'Người liên hệ': ceo,
            'SĐT': clean_phone_val(phone),
            'Liên Hệ': website,
            'Email': email,
            'Liên Hệ mail': '',
            'Địa chỉ': address,
            'Lương': '',
            'Ngày đăng': '',
            'Hạn tuyển': '',
            'Check gửi': '',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trạng thái Reply': '',
            'Lần Follow-up': '',
            'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': category
        }
        enriched_list.append(item)

    print(f"[+] Đã so khớp thành công {matched_knesa_count} công ty từ KNESA vào danh sách MOEL!")

    # 3. Bổ sung các hội viên KNESA chưa có trong MOEL (những công ty có sẵn 100% SĐT di động)
    added_from_knesa = 0
    for k in knesa_all:
        if k['company'] not in matched_knesa_set and not any(ig in k['company'] for ig in ['산모', '베이비', '파출', '간병']):
            item = {
                'No.': '',
                'Công ty': k['company'],
                'Chức danh': 'Đại diện pháp luật',
                'Người liên hệ': k['ceo'],
                'SĐT': clean_phone_val(k.get('mobile') or k.get('tel') or ""),
                'Liên Hệ': k.get('detail_url', ''),
                'Email': '',
                'Liên Hệ mail': '',
                'Địa chỉ': k.get('address', ''),
                'Lương': '',
                'Ngày đăng': '',
                'Hạn tuyển': '',
                'Check gửi': '',
                'Last Subject': '',
                'Last Body HTML': '',
                'Trạng thái Reply': '',
                'Lần Follow-up': '',
                'Ngày Follow-up gần nhất': '',
                'Mailbox đã dùng': '',
                'Category': f"Môi giới nhân lực - {k['branch']} | {k.get('category', '건설/산업')}"
            }
            enriched_list.append(item)
            added_from_knesa += 1

    print(f"[+] Bổ sung thêm {added_from_knesa} hội viên uy tín KNESA có sẵn SĐT di động vào danh sách!")
    print(f"[*] Tổng số doanh nghiệp trong tệp làm giàu: {len(enriched_list)}")

    # 4. Phân loại theo quy chuẩn: ĐẨY 100% DOANH NGHIỆP CÓ EMAIL LÊN ĐẦU
    with_email = [r for r in enriched_list if r.get('Email', '').strip()]
    with_phone_only = [r for r in enriched_list if not r.get('Email', '').strip() and r.get('SĐT', '').strip()]
    without_contact = [r for r in enriched_list if not r.get('Email', '').strip() and not r.get('SĐT', '').strip()]
    final_rows = with_email + with_phone_only + without_contact

    for i, r in enumerate(final_rows, 1):
        r['No.'] = str(i)

    # 5. Xuất file
    with open(OUTPUT_1ENR, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLDMAIL_FIELDNAMES)
        writer.writeheader()
        writer.writerows(final_rows)
    print(f"[OK] Đã xuất {OUTPUT_1ENR}")

    with open(OUTPUT_2COL, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLDMAIL_FIELDNAMES)
        writer.writeheader()
        writer.writerows(final_rows)
    print(f"[OK] Đã xuất {OUTPUT_2COL}")

    os.makedirs(os.path.dirname(FMT_2COL), exist_ok=True)
    with open(FMT_2COL, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLDMAIL_FIELDNAMES)
        writer.writeheader()
        writer.writerows(final_rows)
    print(f"[OK] Đã xuất {FMT_2COL}")

    print("\n" + "=" * 80)
    print(f"TỔNG KẾT:")
    print(f"  • Tổng số công ty: {len(final_rows)}")
    print(f"  • Số công ty ĐÃ CÓ EMAIL: {len(with_email)} (xếp ở đầu tệp)")
    print(f"  • Số công ty ĐÃ CÓ SĐT VÀ ĐỊA CHỈ: {len(with_phone_only)}")
    print("=" * 80)

if __name__ == "__main__":
    main()
