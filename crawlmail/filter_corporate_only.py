# -*- coding: utf-8 -*-
"""
Lọc sạch hộ kinh doanh cá nhân / thợ tự do (SZČO / živnostníci),
chỉ giữ lại 100% pháp nhân công ty (s.r.o., a.s., družstvo, k.s., v.o.s...)
cho các tệp dữ liệu SlovakData.
"""

import sys
import os
import csv
import shutil
from pathlib import Path

# UTF-8 console output
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

CORP_FORMS = {
    'spoločnosť s ručením obmedzeným',
    'akciová spoločnosť',
    'jednoduchá spoločnosť na akcie',
    'komanditná spoločnosť',
    'verejná obchodná spoločnosť',
    'družstvo',
    'európska spoločnosť',
    'štátny podnik',
    'podnik zahraničnej osoby (organizačná zložka podniku zahraničnej osoby)',
    'európske zoskupenie hospodárskych záujmov'
}

def filter_file_to_corporate_only(file_name):
    file_path = ROOT_DIR / file_name
    if not file_path.exists():
        print(f"[-] Không tìm thấy tệp: {file_name}")
        return

    backup_path = ROOT_DIR / f"{file_path.stem}_backup_with_szco.csv"
    if not backup_path.exists():
        shutil.copy2(file_path, backup_path)
        print(f"[*] Đã sao lưu tệp gốc chứa cả SZČO: {backup_path.name}")

    with open(file_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    kept = []
    removed = []

    for r in rows:
        forma = (r.get('Loại hình') or '').strip().lower()
        cname = (r.get('Công ty') or '').strip().lower()

        is_corp = forma in CORP_FORMS
        if not is_corp and 'nešpecifikovaná' in forma:
            if any(term in cname for term in ['s.r.o', 's. r. o', 'a.s', 'a. s', 'spol.', 'sro']):
                is_corp = True

        if is_corp:
            kept.append(r)
        else:
            removed.append(r)

    # Renumber sequentially
    for idx, r in enumerate(kept, 1):
        r['No.'] = str(idx)

    # Write back to file
    with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept)

    print(f"[V] {file_name}:")
    print(f"    - Tổng ban đầu: {len(rows):,} dòng")
    print(f"    - Đã loại bỏ SZČO/Cá nhân: {len(removed):,} dòng")
    print(f"    - Giữ lại 100% Pháp nhân Công ty: {len(kept):,} doanh nghiệp (Đã cập nhật No. 1 -> {len(kept):,})\n")

def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "SK_MTAL_SLVD_0RAW.csv"
    if target == "all":
        for fn in ["SK_MTAL_SLVD_0RAW.csv", "SK_AUTO_SLVD_0RAW.csv", "SK_MECH_SLVD_0RAW.csv"]:
            filter_file_to_corporate_only(fn)
    else:
        filter_file_to_corporate_only(target)

if __name__ == "__main__":
    main()
