import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd
import re

df = pd.read_csv('KR_SHIP_HIPC_0RAW.csv', encoding='utf-8-sig')

print('Count:', len(df))

# Check exact company names
print('Duplicated exact company:', df[df.duplicated(subset=['Cong ty'], keep=False)]['Cong ty'].tolist())

# Check normalized company names
def clean_name(s):
    if not isinstance(s, str): return ''
    return re.sub(r'[\(\)주유회사\s㈜]', '', s).lower()

df['clean_name'] = df['Cong ty'].apply(clean_name)
dup_clean = df[df.duplicated(subset=['clean_name'], keep=False)]
print('Duplicated clean names:', len(dup_clean))
if len(dup_clean) > 0:
    for _, r in dup_clean.iterrows():
        print(f"  {r['Cong ty']} | {r['Category']}")

# Check duplicated phone numbers (if any non-empty)
phones = df[df['SDT'].notna() & (df['SDT'].astype(str).str.strip() != '')]
dup_phones = phones[phones.duplicated(subset=['SDT'], keep=False)]
print('Duplicated phones:', len(dup_phones))
if len(dup_phones) > 0:
    for _, r in dup_phones.iterrows():
        print(f"  {r['Cong ty']} | {r['SDT']} | {r['Category']}")
