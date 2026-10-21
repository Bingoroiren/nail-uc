# -*- coding: utf-8 -*-
"""
Sync Reply Status for SK_AUTO_SLVD_1ENR.csv:
1. Quét toàn bộ workspace (Mail Tracker, các file ColdMail, 2COL...) để tổng hợp map email -> trạng thái phản hồi.
2. Thêm cột 'Trạng thái Reply' vào SK_AUTO_SLVD_1ENR.csv (ngay sau cột 'Email').
3. Đối chiếu và cập nhật trạng thái phản hồi cho các công ty đã lấy email từ các file khác hoặc trong Mail Tracker.
"""

import sys
import os
import csv
from pathlib import Path

# Đảm bảo UTF-8 cho Windows Console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
TARGET_CSV = ROOT_DIR / "SK_AUTO_SLVD_1ENR.csv"

def build_reply_status_map():
    reply_map = {}  # email.lower() -> (source_file, status)

    for fpath in ROOT_DIR.glob("*.csv"):
        fname = fpath.name
        if fname == "SK_AUTO_SLVD_1ENR.csv":
            continue

        try:
            with open(fpath, 'r', encoding='utf-8-sig', errors='ignore') as fp:
                reader = csv.DictReader(fp)
                fields = reader.fieldnames or []

                rep_col = next((c for c in fields if any(k in c.lower() for k in ['trạng thái reply', 'tình trạng phản hồi', 'reply status'])), None)
                mail_col = next((c for c in fields if any(k in c.lower() for k in ['email', 'người gửi', 'mail'])), None)

                if rep_col and mail_col:
                    file_hits = 0
                    for row in reader:
                        m = (row.get(mail_col) or '').strip().lower()
                        rep = (row.get(rep_col) or '').strip()
                        if m and rep:
                            file_hits += 1
                            # Ưu tiên trạng thái tích cực hoặc chi tiết hơn
                            if m not in reply_map or 'reply' in rep.lower() or 'phản hồi' in rep.lower():
                                reply_map[m] = (fname, rep)

                    if file_hits > 0:
                        print(f"[*] Đọc nguồn: {fname:<35} | {file_hits:>3} phản hồi (Cột: {rep_col})")
        except Exception:
            pass

    return reply_map

def sync_replies():
    print("=" * 70)
    print(" BẮT ĐẦU ĐỒNG BỘ TRẠNG THÁI PHẢN HỒI CHO SK_AUTO_SLVD_1ENR.csv")
    print("=" * 70)

    reply_map = build_reply_status_map()
    print(f"\n[+] Tổng cộng phát hiện {len(reply_map):,} email có trạng thái phản hồi trong workspace.\n")

    if not TARGET_CSV.exists():
        print(f"[-] Không tìm thấy file: {TARGET_CSV}")
        return

    with open(TARGET_CSV, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    # Đảm bảo có cột 'Trạng thái Reply' ngay sau 'Email'
    if 'Trạng thái Reply' not in fieldnames:
        if 'Email' in fieldnames:
            idx = fieldnames.index('Email') + 1
            fieldnames.insert(idx, 'Trạng thái Reply')
        else:
            fieldnames.append('Trạng thái Reply')

    updated_rows = []
    updated_count = 0

    for idx, r in enumerate(rows, 1):
        m = (r.get('Email') or '').strip().lower()
        current_reply = (r.get('Trạng thái Reply') or '').strip()

        matched_status = ""
        matched_source = ""

        if m and m in reply_map:
            matched_source, matched_status = reply_map[m]
            r['Trạng thái Reply'] = matched_status
            updated_count += 1
            print(f"  [✓] Dòng {idx:>3}: {r.get('Công ty')} | Email: {r.get('Email')}")
            print(f"       -> Trạng thái phản hồi: '{matched_status}' (Nguồn: {matched_source})")
        else:
            r['Trạng thái Reply'] = current_reply

        updated_rows.append(r)

    # Ghi lại tệp SK_AUTO_SLVD_1ENR.csv
    with open(TARGET_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(updated_rows)

    print("\n" + "=" * 70)
    print(f" HOÀN TẤT ĐỒNG BỘ TRẠNG THÁI PHẢN HỒI!")
    print(f"[*] File đích: {TARGET_CSV.name}")
    print(f"[*] Tổng số bản ghi được cập nhật trạng thái phản hồi: {updated_count}")
    print(f"[*] Cột 'Trạng thái Reply' đã được tích hợp chuẩn xác vào header!")
    print("=" * 70)

if __name__ == '__main__':
    sync_replies()
