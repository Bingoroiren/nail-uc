import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd

df = pd.read_csv('KR_SHIP_HIPC_0RAW.csv', encoding='utf-8-sig')

print('=== HD Hyundai GONGTONG & ENGINE ===')
for idx, r in df[df['Category'].str.contains('공통|엔진')].iterrows():
    print(r['Cong ty'], '|', r['Chuc danh'], '|', r['Category'])

print('\n=== KOSIC COMPANIES ===')
for idx, r in df[df['Category'].str.contains('KOSIC')].iterrows():
    print(f"{r['Cong ty']:20} | {r['Chuc danh']}")
