# -*- coding: utf-8 -*-
"""
KBO DETAIL BACKFILL TOOL - BELGIUM ENTERPRISES
==============================================
Quét nhanh toàn bộ số KBO bằng Multi-threading (Direct HTTP GET, 0% Captcha)
để kéo Email, Website và SĐT chính thức từ cổng chính phủ FOD Economie
bổ sung trực tiếp vào các file RAW KBO.
"""

import sys
import re
import csv
import time
import argparse
import urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

def clean_kbo_num(kbo_raw):
    return re.sub(r'[^0-9]', '', str(kbo_raw or ''))

def fetch_kbo_detail(kbo_raw):
    clean_num = clean_kbo_num(kbo_raw)
    if not clean_num or len(clean_num) < 9:
        return {'kbo': kbo_raw, 'email': '', 'web': '', 'tel': ''}
    
    url = f"https://kbopub.economie.fgov.be/kbopub/toonondernemingps.html?ondernemingsnummer={clean_num}"
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    })
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            soup = BeautifulSoup(html, 'html.parser')
            email, web, tel = '', '', ''
            for tr in soup.find_all('tr'):
                txt = tr.get_text(separator=' | ', strip=True)
                txt_l = txt.lower()
                if 'e-mail:' in txt_l and 'geen gegevens' not in txt_l:
                    m = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', txt)
                    if m:
                        email = m.group(0).lower()
                if 'webadres:' in txt_l and 'geen gegevens' not in txt_l:
                    parts = [p.strip() for p in txt.split('|') if 'webadres' not in p.lower() and 'sinds' not in p.lower() and '(' not in p]
                    if parts:
                        web = parts[0]
                if 'telefoonnummer:' in txt_l and 'geen gegevens' not in txt_l:
                    m = re.search(r'0032\d+|0\d{8,9}|\+32\d+', txt)
                    if m:
                        t = m.group(0)
                        tel = f"'{t}" if not t.startswith("'") else t
            return {'kbo': kbo_raw, 'email': email, 'web': web, 'tel': tel}
    except Exception:
        return {'kbo': kbo_raw, 'email': '', 'web': '', 'tel': ''}

def backfill_file(csv_path, max_workers=12):
    p = Path(csv_path)
    if not p.is_absolute():
        p = ROOT_DIR / p
    if not p.exists():
        print(f"[!] Không tìm thấy tệp {p.name}")
        return

    print("=" * 80)
    print(f"🇧🇪  ĐANG BỔ SUNG EMAIL/WEB CHÍNH THỨC TỪ KBO CHO: {p.name}")
    print("=" * 80)

    rows = []
    with open(p, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        for r in reader:
            rows.append(r)

    if 'Email' not in fields:
        idx = fields.index('Phone') + 1 if 'Phone' in fields else len(fields)
        fields.insert(idx, 'Email')

    unique_kbos = list(dict.fromkeys([r.get('KBO_Number') for r in rows if r.get('KBO_Number') and r.get('KBO_Number') != '-']))
    print(f"[*] Tổng số dòng: {len(rows):,} | Số mã KBO độc nhất cần tra cứu: {len(unique_kbos):,}")
    print(f"[*] Đang tra cứu đồng thời với {max_workers} luồng...", flush=True)

    contact_map = {}
    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for res in executor.map(fetch_kbo_detail, unique_kbos):
            done += 1
            if res:
                contact_map[res['kbo']] = res
            if done % 200 == 0 or done == len(unique_kbos):
                pct = done * 100 / len(unique_kbos)
                print(f"  -> Tiến độ tra cứu KBO: {done:,}/{len(unique_kbos):,} ({pct:.1f}%)", flush=True)

    new_emails = 0
    new_webs = 0
    new_phones = 0
    for r in rows:
        kbo_val = r.get('KBO_Number')
        c = contact_map.get(kbo_val)
        if c:
            if c['email'] and not r.get('Email'):
                r['Email'] = c['email']
                new_emails += 1
            if c['web'] and not r.get('Website'):
                r['Website'] = c['web']
                new_webs += 1
            if c['tel'] and not r.get('Phone'):
                r['Phone'] = c['tel']
                new_phones += 1

    with open(p, mode='w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print("\n" + "=" * 80)
    print(f"🏆 HOÀN THÀNH BỔ SUNG KBO CHO {p.name}:")
    print(f"   - Email chính thức bổ sung mới : +{new_emails:,}")
    print(f"   - Website bổ sung mới          : +{new_webs:,}")
    print(f"   - SĐT bổ sung mới              : +{new_phones:,}")
    print("=" * 80 + "\n")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="KBO Detail Contact Backfill Tool")
    parser.add_argument("file", help="Tên hoặc đường dẫn file CSV RAW KBO (ví dụ: BE_MEAT_KBO0_0RAW.csv)")
    parser.add_argument("--workers", type=int, default=12, help="Số luồng chạy đồng thời (mặc định 12)")
    args = parser.parse_args()

    backfill_file(args.file, max_workers=args.workers)

