import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd
import re

df = pd.read_csv('KR_SHIP_HIPC_0RAW.csv', encoding='utf-8-sig')

def norm(name):
    if not isinstance(name, str): return ''
    n = re.sub(r'[\(\)주유회사\s㈜\.\,\-\_]', '', name)
    return n.lower()

df['norm_name'] = df['Cong ty'].apply(norm)

# 1. Internal near duplicates (same representative + similar name)
reps = {}
for idx, r in df.iterrows():
    rep = str(r.get('Nguoi lien he', '')).strip()
    if rep and rep != 'nan':
        reps.setdefault(rep, []).append((idx+1, r['Cong ty'], r['Category']))

print("=== REPRESENTATIVES WITH MULTIPLE ENTRIES ===")
for rep, entries in reps.items():
    if len(entries) > 1:
        print(f"Rep '{rep}':")
        for e in entries:
            print(f"   Row {e[0]}: {e[1]} ({e[2]})")

# 2. Check overlap with KR_SHIP_DSTU_2COL
dstu = pd.read_csv('KR_SHIP_DSTU_2COL.csv', encoding='utf-8-sig')
dstu['norm_name'] = dstu['Công ty'].apply(norm)
overlap_dstu = df[df['norm_name'].isin(set(dstu['norm_name']))]
print(f"\n=== OVERLAP WITH KR_SHIP_DSTU_2COL ({len(overlap_dstu)} companies) ===")
for idx, r in overlap_dstu.iterrows():
    print(f"Row {idx+1}: {r['Cong ty']} | {r['Category']}")

# 3. Check overlap with KR_WELD_E703_2COL
weld = pd.read_csv('KR_WELD_E703_2COL.csv', encoding='utf-8-sig')
weld['norm_name'] = weld['Cong ty'].apply(norm)
overlap_weld = df[df['norm_name'].isin(set(weld['norm_name']))]
print(f"\n=== OVERLAP WITH KR_WELD_E703_2COL ({len(overlap_weld)} companies) ===")
for idx, r in overlap_weld.iterrows():
    print(f"Row {idx+1}: {r['Cong ty']} | {r['Category']}")

# 4. Check leisure / sports boat / non-shipbuilding in KOSIC
print("\n=== LEISURE / SPORTS BOAT / SMALL BOAT MAKERS ===")
leisure_keywords = ['요트', '보트', '서핑', '수상레저', '오락']
for idx, r in df.iterrows():
    title = str(r.get('Chuc danh', ''))
    if any(k in title for k in leisure_keywords):
        print(f"Row {idx+1}: {r['Cong ty']} | {title}")
