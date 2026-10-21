# -*- coding: utf-8 -*-
"""
Chuẩn hóa SK_MANU_ZLAT_0RAW.csv sang chuẩn Cold Mail 20 cột: SK_MANU_ZLAT_2COL.csv
- Lọc bỏ mail rác / tracking / sentry
- SĐT chuẩn hóa với nháy đơn '
- Đẩy 100% doanh nghiệp có Email lên các dòng đầu tiên (No. 1 -> N)
- Phân tích chi tiết tỷ lệ Email & Domain
"""

import sys
import os
import re
import csv
from collections import Counter
from urllib.parse import urlparse

COLDMAIL_COLUMNS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

JUNK_SUBSTRINGS = [
    'sentry.io', 'wixpress.com', 'domain.com', 'example.com',
    'yourcompany', 'youremail', 'yourdomain', 'name@email.com'
]

JUNK_PREFIXES = (
    'sentry@', 'noreply@', 'no-reply@', 'donotreply@',
    'privacy@', 'gdpr@', 'dataprivacy@', 'datenschutz@'
)

def clean_phone(p):
    if not p:
        return ''
    p = str(p).strip().lstrip("'")
    digits = re.sub(r'[^\d+]', '', p)
    if not digits:
        return ''
    if digits.startswith('+'):
        return f"'{digits}"
    elif digits.startswith('421'):
        return f"'+{digits}"
    elif digits.startswith('0'):
        return f"'+421{digits[1:]}"
    return f"'+421{digits}"

def clean_email(em):
    if not em:
        return ''
    e = em.replace('%20', '').strip().lower().rstrip('.,;:/')
    if '@' not in e or '.' not in e:
        return ''
    if any(e.startswith(p) for p in JUNK_PREFIXES):
        return ''
    if any(j in e for j in JUNK_SUBSTRINGS):
        return ''
    return e

def main():
    with_email = []
    without_email = []
    email_types = Counter()

    with open('SK_MANU_ZLAT_0RAW.csv', mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            cname = row.get('Công ty', '').strip()
            web = row.get('Liên Hệ', '').strip()
            phone = clean_phone(row.get('SĐT', ''))
            email = clean_email(row.get('Email', ''))
            addr = row.get('Địa chỉ', '').strip()
            cat = row.get('Category', '').strip()

            new_row = {
                'No.': '',
                'Công ty': cname,
                'Chức danh': '',
                'Người liên hệ': '',
                'SĐT': phone,
                'Liên Hệ': web,
                'Email': email,
                'Liên Hệ mail': '',
                'Địa chỉ': addr,
                'Lương': '',
                'Ngày đăng': '',
                'Hạn tuyển': '',
                'Check gửi': 'OK' if email else '',
                'Last Subject': '',
                'Last Body HTML': '',
                'Trạng thái Reply': '',
                'Lần Follow-up': '0',
                'Ngày Follow-up gần nhất': '',
                'Mailbox đã dùng': '',
                'Category': cat
            }

            if email:
                with_email.append(new_row)
                dom = email.split('@')[-1]
                if any(x in dom for x in ['gmail.com', 'zoznam.sk', 'seznam.cz', 'centrum.sk', 'post.sk', 'azet.sk']):
                    email_types['Free Webmail (Gmail, Zoznam, Seznam...)'] += 1
                else:
                    email_types['Corporate Domain (Domain riêng doanh nghiệp)'] += 1
            else:
                without_email.append(new_row)

    total = len(with_email) + len(without_email)
    all_rows = with_email + without_email

    for idx, r in enumerate(all_rows, start=1):
        r['No.'] = str(idx)

    with open('SK_MANU_ZLAT_2COL.csv', mode='w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLDMAIL_COLUMNS)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"TOTAL: {total}")
    print(f"WITH_EMAIL: {len(with_email)} ({len(with_email)/total*100:.2f}%)")
    print(f"WITHOUT_EMAIL: {len(without_email)} ({len(without_email)/total*100:.2f}%)")
    for etype, cnt in email_types.items():
        print(f" - {etype}: {cnt} ({cnt/len(with_email)*100:.1f}%)")

if __name__ == '__main__':
    main()
