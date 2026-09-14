import csv

path = r'(10_9) Nông trại na uy - Trang tính1.csv'
with open(path, mode='r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

for i, r in enumerate(rows):
    e = r.get('Email', '').strip()
    if e:
        print(f"{i+1}: {r.get('Cong ty', '')[:25]} | {r.get('Lien He', '')[:35]} | {e}")
