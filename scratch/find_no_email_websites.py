# -*- coding: utf-8 -*-
import csv

with open('agency phần lan (đã lọc trùng).csv', 'r', encoding='utf-8') as f:
    r = csv.DictReader(f)
    no_email_with_web = [row for row in r if not row.get('email') and row.get('website')]
    print(f'Total with website but no email: {len(no_email_with_web)}')
    for row in no_email_with_web[:15]:
        print(f"{row['name']} -> {row['website']}")
