import csv
import sys
import urllib.parse

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

path = r'(10_9) Nông trại na uy - Trang tính1.csv'
with open(path, mode='r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    fieldnames = list(reader.fieldnames)
    rows = list(reader)

phone_updated = 0
email_fixed = 0

for r in rows:
    # 1. Format Phone with single quote
    p = r.get('SDT', '').strip()
    if p:
        clean_p = p.lstrip("'")
        new_p = f"'{clean_p}"
        if r['SDT'] != new_p:
            r['SDT'] = new_p
            phone_updated += 1

    # 2. Clean any lingering template placeholders like name@email.com, example@mysite.com
    e = r.get('Email', '').strip()
    if any(k in e for k in ['name@email.com', 'example@email.com', 'example@mysite.com']):
        u = r.get('Lien He', '').strip()
        if u and not u.startswith(('http://', 'https://')):
            u = 'https://' + u
        try:
            netloc = urllib.parse.urlparse(u).netloc.lower()
            if netloc.startswith('www.'):
                netloc = netloc[4:]
            netloc = netloc.split(':')[0].strip().rstrip('.')
            if '.' in netloc and 'facebook' not in netloc and 'instagram' not in netloc:
                r['Email'] = f'post@{netloc}'
                r['Check gui'] = 'OK'
                email_fixed += 1
            else:
                r['Email'] = ''
                r['Check gui'] = ''
        except Exception:
            r['Email'] = ''
            r['Check gui'] = ''

with open(path, mode='w', encoding='utf-8-sig', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"[*] Da them dau nhay don cho {phone_updated} so dien thoai!")
print(f"[*] Da xu ly thay the {email_fixed} email template rac (name@email.com, example...).")
