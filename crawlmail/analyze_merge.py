# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd
import re

def norm(name):
    if not isinstance(name, str): return ''
    n = re.sub(r'[\(\)주유회사\s㈜\.\,\-\_]', '', name)
    return n.lower()

# ============================================================
# NHÓM 1: ĐÓNG TÀU (HIPC + WELD)
# ============================================================
hipc = pd.read_csv('KR_SHIP_HIPC_2COL.csv', encoding='utf-8-sig')
weld = pd.read_csv('KR_WELD_E703_2COL.csv', encoding='utf-8-sig')
hipc['norm'] = hipc['Cong ty'].apply(norm)
weld['norm'] = weld['Cong ty'].apply(norm)

overlap_ship = set(hipc['norm']).intersection(set(weld['norm']))
all_ship = pd.concat([hipc, weld], ignore_index=True)
all_ship_dedup = all_ship.drop_duplicates(subset=['norm'], keep='first')

has_email_ship = all_ship_dedup[all_ship_dedup['Email'].notna() & (all_ship_dedup['Email'].astype(str).str.strip() != '')]
has_phone_ship = all_ship_dedup[all_ship_dedup['SDT'].notna() & (all_ship_dedup['SDT'].astype(str).str.strip() != '')]

print("=" * 65)
print("NHÓM 1: ĐÓNG TÀU & THẦU PHỤ (HIPC + WELD)")
print("=" * 65)
print(f"  - KR_SHIP_HIPC_2COL.csv : {len(hipc)} công ty (123 thầu phụ Hyundai Ulsan + 60 KOSIC)")
print(f"  - KR_WELD_E703_2COL.csv : {len(weld)} công ty (Xưởng tuyển thợ hàn Work24/Saramin)")
print(f"  - Trùng lặp giữa 2 tệp  : {len(overlap_ship)} công ty ({overlap_ship})")
print(f"  -> Tổng sau khi gộp & khử trùng: {len(all_ship_dedup)} công ty")
print(f"  -> Số công ty có Email B2B      : {len(has_email_ship)}")
print(f"  -> Số công ty có SĐT            : {len(has_phone_ship)}")

# ============================================================
# NHÓM 2: TÀU TUYỂN THỦY THỦ / HÃNG TÀU (DSTU)
# ============================================================
dstu = pd.read_csv('KR_SHIP_DSTU_2COL.csv', encoding='utf-8-sig')
crew_dstu = dstu[~dstu['Category'].str.contains('기자재|Vật tư', na=False)].copy()
equip_dstu = dstu[dstu['Category'].str.contains('기자재|Vật tư', na=False)].copy()

has_email_crew = crew_dstu[crew_dstu['Email'].notna() & (crew_dstu['Email'].astype(str).str.strip() != '')]

print("\n" + "=" * 65)
print("NHÓM 2: TÀU TUYỂN THỦY THỦ / HÃNG TÀU BIỂN (DSTU)")
print("=" * 65)
print(f"  - Toàn bộ KR_SHIP_DSTU_2COL.csv        : {len(dstu)} dòng")
print(f"  - Phân hệ Hãng tàu tuyển thuyền viên   : {len(crew_dstu)} công ty (Seanet, Viễn dương, Tanker, Tàu kéo)")
print(f"  - Phân hệ Vật tư & Thiết bị đóng tàu   : {len(equip_dstu)} công ty (조선기자재)")
print(f"  -> Số hãng tàu có Email B2B xác thực   : {len(has_email_crew)}")

# ============================================================
# NHÓM 3: AGENCY MÔI GIỚI & NHÂN LỰC (NVER + MOEL)
# ============================================================
nver = pd.read_csv('KR_AGCY_NVER_2COL.csv', encoding='utf-8-sig')
moel = pd.read_csv('KR_AGCY_MOEL_0RAW.csv', encoding='utf-8-sig')
nver['norm'] = nver['Cong ty'].apply(norm)
moel['norm'] = moel['Cong ty'].apply(norm)

overlap_agcy = set(nver['norm']).intersection(set(moel['norm']))
all_agcy = pd.concat([nver, moel], ignore_index=True)
all_agcy_dedup = all_agcy.drop_duplicates(subset=['norm'], keep='first')

has_email_agcy = all_agcy_dedup[all_agcy_dedup['Email'].notna() & (all_agcy_dedup['Email'].astype(str).str.strip() != '')]
has_phone_agcy = all_agcy_dedup[all_agcy_dedup['SDT'].notna() & (all_agcy_dedup['SDT'].astype(str).str.strip() != '')]

print("\n" + "=" * 65)
print("NHÓM 3: AGENCY MÔI GIỚI & NHÂN LỰC (NVER + MOEL)")
print("=" * 65)
print(f"  - KR_AGCY_NVER_2COL.csv : {len(nver)} công ty (Naver Maps 인력/직업소개소/파견)")
print(f"  - KR_AGCY_MOEL_0RAW.csv : {len(moel)} công ty (Được Bộ Lao động MOEL cấp phép)")
print(f"  - Trùng lặp giữa 2 tệp  : {len(overlap_agcy)} công ty")
print(f"  -> Tổng sau khi gộp & khử trùng: {len(all_agcy_dedup)} công ty")
print(f"  -> Số Agency có Email B2B      : {len(has_email_agcy)}")
print(f"  -> Số Agency có SĐT            : {len(has_phone_agcy)}")
