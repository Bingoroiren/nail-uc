# -*- coding: utf-8 -*-
"""
Lọc trùng lặp & Loại bỏ công ty không liên quan cho KR_WELD_E703_0RAW.csv
Giữ lại 100% công ty/xưởng đóng tàu và thầu phụ thực sự tuyển thợ hàn/thợ đóng tàu E-7-3.
"""

import os
import sys
import re
import csv
import pandas as pd
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT_DIR / "KR_WELD_E703_0RAW.csv"

EXCLUDE_KEYWORDS = [
    '소프트웨어', 'sw개발', 'ai로봇', '웹개발', '앱개발', '연구원', '전문연구요원', 
    '병역특례', '석사', '박사', '경영지원', '사무영업', '번역', '통역', '경리', 
    '회계', '식품', '수산', '베이커리', '음료', '병원', '간호', '약사', 
    '보험', '카드', '부동산', '학원', '강사', '한국선급', '대학교', '초중고'
]

SHIP_WELD_KEYWORDS = [
    '용접', '취부', '사상', '취부사', '용접사', '배관', '조선', '선박', 
    '중공업', '해양', '플랜트', '사내협력사', '조선소', '선체', '도장', 
    '의장', '제작', '제관', '철골', '가공', '선반', '밀링', '탱크', 
    '취부원', '용접원', 'co2', 'tig', 'fcaw', 'mig', '선박부품', '선박기자재'
]

SHIP_HUBS = [
    '울산', '거제', '영암', '목포', '통영', '창원', '진해', '부산', 
    '해남', '광양', '신안', '여수', '포항', '사천', '김해'
]

def normalize_key(name):
    n = re.sub(r'[\(\)\[\]\{\}주식회사㈜유한회사]+', '', name).strip().lower()
    n = re.sub(r'\s+', '', n)
    return n

def main():
    if not CSV_PATH.exists():
        print(f"[!] Không tìm thấy tệp {CSV_PATH}")
        return

    df = pd.read_csv(CSV_PATH, dtype=str).fillna("")
    print(f"Tổng số ban đầu: {len(df)} công ty")

    # 1. Khử trùng lặp theo tên chuẩn hóa
    unique_map = {}
    for idx, r in df.iterrows():
        cname = r["Cong ty"].strip()
        k = normalize_key(cname)
        if not k or len(k) < 2:
            continue
            
        if k not in unique_map:
            unique_map[k] = r.to_dict()
        else:
            # Gộp thông tin
            ex = unique_map[k]
            if r["Chuc danh"] not in ex["Chuc danh"]:
                ex["Chuc danh"] += f" | {r['Chuc danh']}"
            if len(r["Dia chi"]) > len(ex["Dia chi"]):
                ex["Dia chi"] = r["Dia chi"]
            if r["Han tuyen"] and not ex["Han tuyen"]:
                ex["Han tuyen"] = r["Han tuyen"]

    deduped = list(unique_map.values())
    print(f"Sau khi khử trùng lặp chặt chẽ: {len(deduped)} công ty")

    # 2. Lọc bỏ các công ty không liên quan
    filtered = []
    discarded = []

    for item in deduped:
        comp = item["Cong ty"].strip()
        tit = item["Chuc danh"].lower()
        loc = item["Dia chi"]
        full_text = f"{comp} {tit} {loc}".lower()

        # Loại trừ nếu dính từ khóa đen
        excluded = False
        for kw in EXCLUDE_KEYWORDS:
            if kw in full_text:
                if not ('조선' in comp or '용접' in comp or '사내협력사' in tit or '취부' in tit):
                    excluded = True
                    discarded.append((comp, tit[:40], kw))
                    break
        if excluded:
            continue

        # Kiểm tra tiêu chí ngành đóng tàu & thợ hàn E-7-3
        has_weld = any(k in full_text for k in SHIP_WELD_KEYWORDS)
        in_hub = any(h in loc for h in SHIP_HUBS)

        if has_weld or in_hub:
            filtered.append(item)
        else:
            discarded.append((comp, tit[:40], "Non-ship/Non-hub"))

    print(f"Đã loại bỏ: {len(discarded)} công ty không phù hợp.")
    print(f"-> SỐ DOANH NGHIỆP GIỮ LẠI (CHUẨN E-7-3 100%): {len(filtered)} công ty.")

    # 3. Ghi lại vào KR_WELD_E703_0RAW.csv
    headers = list(df.columns)
    final_rows = []
    for idx, item in enumerate(filtered, 1):
        item["No."] = str(idx)
        row = [item.get(c, "") for c in headers]
        final_rows.append(row)

    with open(CSV_PATH, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(final_rows)

    print(f"[V] Đã cập nhật tệp làm sạch: {CSV_PATH} ({len(final_rows)} công ty)")

if __name__ == "__main__":
    main()
