import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd

df = pd.read_csv('KR_AGCY_MOEL_0RAW.csv', encoding='utf-8-sig')
no_contact = df[df['Email'].isna() | (df['Email'].str.strip() == '')]
samples = no_contact.iloc[10:25]
for idx, r in samples.iterrows():
    c = r['Cong ty']
    rep = str(r['Nguoi lien he'])
    addr = str(r['Dia chi'])
    print(r['No.'], '|', c, '|', rep, '|', addr)
