# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd
import re

df = pd.read_csv('KR_AGCY_MOEL_0RAW.csv', encoding='utf-8-sig')

GARBAGE = ['sentry', 'wixpress', 'wix.com', 'monday.com', 'wordpress', 'no-reply', 'donotreply', 'privacy@', 'gdpr@']

def clean_em(e):
    if pd.isna(e) or not str(e).strip() or str(e) == 'nan': return ''
    s = str(e).strip().lower()
    for g in GARBAGE:
        if g in s:
            return ''
    if not re.search(r'\.[a-z]{2,}$', s):
        return ''
    return s

df['Email'] = df['Email'].apply(clean_em)

# Sort again: with email first, then with sdt, then remaining
has_em = df['Email'].str.strip() != ''
has_ph = df['SDT'].notna() & (df['SDT'].astype(str).str.strip() != '') & (df['SDT'].astype(str) != 'nan')

p1 = df[has_em].copy()
p2 = df[~has_em & has_ph].copy()
p3 = df[~has_em & ~has_ph].copy()

df_sorted = pd.concat([p1, p2, p3], ignore_index=True)
df_sorted['No.'] = range(1, len(df_sorted) + 1)
df_sorted.to_csv('KR_AGCY_MOEL_0RAW.csv', index=False, encoding='utf-8-sig')

print('Cleaned! Total valid B2B emails:', len(p1))
print('Total with Phone:', len(df_sorted[df_sorted['SDT'].notna() & (df_sorted['SDT'].astype(str).str.strip() != '')]))

print('\nTop 10 verified emails:')
for idx, r in p1.head(10).iterrows():
    c = r['Cong ty']
    sdt = r['SDT']
    em = r['Email']
    addr = str(r['Dia chi'])[:35]
    print(f"  {idx+1:2d}. {c:22} | SĐT: {str(sdt):16} | Email: {str(em):25} | {addr}")
