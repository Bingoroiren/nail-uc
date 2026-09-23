import csv, sys
sys.stdout.reconfigure(encoding='utf-8')

with open('NOPODATA.csv', encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))

has_email = [r for r in rows if r.get('email', '').strip()]
has_web = [r for r in rows if r.get('website', '').strip()]
has_phone = [r for r in rows if r.get('phone', '').strip()]
check_gui = [r for r in rows if r.get('Check gui', '').strip() == 'OK']

print(f"Tổng số bản ghi: {len(rows)}")
print(f"Số Email hiện tại: {len(has_email)} (tăng từ 13 ban đầu)")
print(f"Số Website hiện tại: {len(has_web)} (tăng từ 13 ban đầu)")
print(f"Số SĐT hiện tại: {len(has_phone)}")
print(f"Số bản ghi Check gui = OK: {len(check_gui)}")
print("\nMẫu các email mới được tìm thấy và làm giàu:")
for r in has_email[13:28]:
    print(f"  + {r['name'][:35]:<35} | {r['email']:<30} | {r.get('website','')}")
