# -*- coding: utf-8 -*-
import sys, re, pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

df_tracker = pd.read_csv('Mail Tracker - mail.csv', encoding='utf-8-sig', dtype=str).fillna('')
tracker_emails = {}
tracker_corp_domains = {}
generic_domains = {'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'centrum.sk', 'centrum.cz', 'zoznam.sk', 'post.sk', 'azet.sk', 'seznam.cz'}

for idx, r in df_tracker.iterrows():
    nguoi_gui = str(r.get('Người gửi', '')).strip().lower()
    subject = str(r.get('Subject', '')).strip()
    tinh_trang = str(r.get('Tình trạng phản hồi', '')).strip()
    note_str = tinh_trang if tinh_trang else (subject if subject else 'Ghi nhận trong Mail Tracker')
    for em in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', nguoi_gui):
        if not any(k in em for k in ['glcquocte', 'workforce.asia', 'mobilityworks.asia']):
            tracker_emails[em] = note_str
            d = em.split('@')[1]
            if d not in generic_domains:
                tracker_corp_domains[d] = note_str

tracker_base_domains = {}
for d, note in tracker_corp_domains.items():
    base = d.split('.')[0]
    if len(base) >= 5 and base not in ['gmail', 'yahoo', 'hotmail', 'outlook', 'centrum', 'zoznam', 'post', 'azet', 'seznam', 'inbox']:
        tracker_base_domains[base] = (d, note)

df_master = pd.read_csv('SK_AGCY_ALL_2COL.csv', encoding='utf-8-sig', dtype=str).fillna('')
for idx, r in df_master.iterrows():
    em = r['Email'].strip().lower()
    comp = r['Công ty'].strip()
    if em and '@' in em:
        d = em.split('@')[1]
        base = d.split('.')[0]
        if base in tracker_base_domains and d not in tracker_corp_domains and em not in tracker_emails:
            orig_d, note = tracker_base_domains[base]
            print(f"Matched base: {comp} | {em} -> Base '{base}' (from {orig_d} - {note})")
