import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd
import re

def norm(name):
    if not isinstance(name, str): return ''
    n = re.sub(r'[\(\)주유회사\s㈜\.\,\-\_]', '', name)
    return n.lower()

dstu = pd.read_csv('KR_SHIP_DSTU_2COL.csv', encoding='utf-8-sig')
dstu['norm'] = dstu['Công ty'].apply(norm)

hipc = pd.read_csv('KR_SHIP_HIPC_0RAW.csv', encoding='utf-8-sig')
hipc['norm'] = hipc['Cong ty'].apply(norm)

merged = hipc.merge(dstu, on='norm', suffixes=('_hipc', '_dstu'))
print(f'Matched {len(merged)} companies from DSTU.')
for idx, r in merged.head(10).iterrows():
    c = r['Cong ty']
    sdt = r.get('SĐT', '')
    web = r.get('Liên Hệ', '')
    em = r.get('Email_dstu', '')
    print(f"{c:20} | SDT: {sdt} | Web: {web} | Email: {em}")
