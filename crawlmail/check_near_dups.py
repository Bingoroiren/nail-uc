import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd
import re

df = pd.read_csv('KR_SHIP_HIPC_0RAW.csv', encoding='utf-8-sig')

def clean(s):
    if not isinstance(s, str): return ''
    return re.sub(r'[\(\)주유회사\s㈜\.\,\-\_]', '', s).lower()

names = df['Cong ty'].tolist()
cleaned = [clean(n) for n in names]

print("=== CHECKING INTERNAL NEAR-DUPLICATES ===")
found_near = False
for i in range(len(names)):
    for j in range(i+1, len(names)):
        n1, n2 = cleaned[i], cleaned[j]
        # Check if one is substring of other and difference is just generic words like 기업, 산업, 조선, 이엔지, eng, 테크, etc.
        core1 = re.sub(r'(기업|산업|조선|이엔지|eng|테크|중공업|마린|선박|기술|플랜트)$', '', n1)
        core2 = re.sub(r'(기업|산업|조선|이엔지|eng|테크|중공업|마린|선박|기술|플랜트)$', '', n2)
        if len(core1) >= 2 and len(core2) >= 2 and core1 == core2:
            print(f"Near match: Row {i+1} [{names[i]} - {df.iloc[i]['Category']}] <-> Row {j+1} [{names[j]} - {df.iloc[j]['Category']}]")
            found_near = True

if not found_near:
    print("No internal near-duplicates found.")
