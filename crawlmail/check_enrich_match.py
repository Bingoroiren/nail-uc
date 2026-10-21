# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd
import re

def norm(name):
    if not isinstance(name, str): return ''
    n = re.sub(r'[\(\)주유회사\s㈜\.\,\-\_\[\]]', '', name)
    return n.lower()

moel = pd.read_csv('KR_AGCY_MOEL_0RAW.csv', encoding='utf-8-sig')
comb = pd.read_csv('KR_AGCY_COMB_2COL.csv', encoding='utf-8-sig')

print(f"MOEL rows: {len(moel)}")
print(f"COMB rows: {len(comb)}")

moel['norm'] = moel['Cong ty'].apply(norm)
comb['norm'] = comb['Cong ty'].apply(norm)

# Check overlap by norm name
comb_with_contact = comb[
    (comb['SDT'].notna() & (comb['SDT'].astype(str).str.strip() != '')) |
    (comb['Email'].notna() & (comb['Email'].astype(str).str.strip() != '')) |
    (comb['Lien He'].notna() & (comb['Lien He'].astype(str).str.strip() != '') & (~comb['Lien He'].astype(str).str.contains('moel.go.kr', na=False)))
].copy()

print(f"COMB rows with contact info: {len(comb_with_contact)}")

matched = moel.merge(comb_with_contact, on='norm', suffixes=('_moel', '_comb'))
print(f"Matched companies: {len(matched)}")
print(f"Unique matched companies in MOEL: {matched['norm'].nunique()}")

has_phone = matched[matched['SDT_comb'].notna() & (matched['SDT_comb'].astype(str).str.strip() != '')]
has_email = matched[matched['Email_comb'].notna() & (matched['Email_comb'].astype(str).str.strip() != '')]
has_web = matched[matched['Lien He_comb'].notna() & (matched['Lien He_comb'].astype(str).str.strip() != '') & (~matched['Lien He_comb'].astype(str).str.contains('moel.go.kr', na=False))]

print(f"Matched with SĐT: {len(has_phone)}")
print(f"Matched with Email: {len(has_email)}")
print(f"Matched with Website: {len(has_web)}")

# Sample matches
print("\nSample 10 matched companies:")
for idx, r in matched.head(10).iterrows():
    c = r['Cong ty_moel']
    sdt = r.get('SDT_comb', '')
    em = r.get('Email_comb', '')
    web = r.get('Lien He_comb', '')
    addr_moel = r.get('Dia chi_moel', '')
    addr_comb = r.get('Dia chi_comb', '')
    print(f"{c:25} | SĐT: {str(sdt):15} | Email: {str(em):20} | Địa chỉ MOEL: {addr_moel} | Naver: {addr_comb[:30]}")
