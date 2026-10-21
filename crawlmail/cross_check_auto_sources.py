# -*- coding: utf-8 -*-
"""
Cross-check SK_AUTO_SLVD_0RAW.csv against all existing datasets & caches in workspace
to find matching companies with Phone, Web, and Email.
"""

import sys
import os
import re
import csv
import json
import glob
from pathlib import Path

# UTF-8 console output
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

LEGAL_FORMS = [
    'spol. s r.o.', 'spol. s r. o.', 's.r.o.', 's. r. o.', 'sro',
    'akciova spolocnost', 'akciová spoločnosť', 'a.s.', 'a. s.', 'as',
    'komanditna spolocnost', 'komanditná spoločnosť', 'k.s.', 'k. s.',
    'verejna obchodna spolocnost', 'verejná obchodná spoločnosť', 'v.o.s.', 'v. o. s.',
    'druzstvo', 'družstvo', 'gmbh', 'ltd', 'inc.'
]

def norm_name(n):
    if not n:
        return ''
    n = re.sub(r'["\'„“”«»]', '', str(n)).strip().lower()
    for lf in sorted(LEGAL_FORMS, key=len, reverse=True):
        pattern = rf'(?:^|[\s,;]){re.escape(lf)}(?:$|[\s,;])'
        n = re.sub(pattern, ' ', n)
    n = re.sub(r'\b(s\s*r\s*o|a\s*s|k\s*s|v\s*o\s*s)\b', ' ', n)
    n = re.sub(r'[^\w\s]', ' ', n)
    return re.sub(r'\s+', ' ', n).strip()

def run_cross_check():
    auto_file = ROOT_DIR / "SK_AUTO_SLVD_0RAW.csv"
    if not auto_file.exists():
        print("[-] Không tìm thấy SK_AUTO_SLVD_0RAW.csv")
        return

    auto_by_ico = {}
    auto_by_name = {}

    with open(auto_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for r in reader:
            ico = (r.get('IČO') or '').strip()
            cname = (r.get('Công ty') or '').strip()
            nname = norm_name(cname)
            entry = {
                'ico': ico,
                'name': cname,
                'norm_name': nname,
                'city': r.get('Thành phố', ''),
                'matches': []
            }
            if ico:
                auto_by_ico[ico] = entry
            if nname and len(nname) >= 3:
                auto_by_name[nname] = entry

    print(f"[*] Đã tải danh sách Ô tô mục tiêu: {len(auto_by_ico):,} IČO, {len(auto_by_name):,} tên công ty đã chuẩn hóa.\n")

    # 1. Quét các tệp CSV
    csv_files = glob.glob(str(ROOT_DIR / "*.csv"))
    print("=" * 65)
    print("1. KẾT QUẢ ĐỐI CHIẾU TRÊN CÁC FILE CSV CÓ SẴN TRONG WORKSPACE:")
    print("=" * 65)

    all_matched_entries = {}  # target_ico/name -> best info

    for fpath in sorted(csv_files):
        fname = os.path.basename(fpath)
        if 'SK_AUTO_SLVD' in fname:
            continue

        try:
            with open(fpath, 'r', encoding='utf-8-sig', errors='ignore') as f:
                reader = csv.DictReader(f)
                fields = reader.fieldnames or []

                ico_col = next((c for c in fields if c.lower() in ['ico', 'ičo']), None)
                name_col = next((c for c in fields if any(k in c.lower() for k in ['công ty', 'company', 'firma', 'name'])), None)
                web_col = next((c for c in fields if any(k in c.lower() for k in ['web', 'website', 'url'])), None)
                mail_col = next((c for c in fields if any(k in c.lower() for k in ['email', 'mail'])), None)
                phone_col = next((c for c in fields if any(k in c.lower() for k in ['sđt', 'phone', 'tel'])), None)

                if not name_col and not ico_col:
                    continue

                file_matches = []
                for row in reader:
                    ico = (row.get(ico_col) or '').strip() if ico_col else ''
                    name = (row.get(name_col) or '').strip() if name_col else ''
                    nname = norm_name(name)

                    target = None
                    m_type = ''
                    if ico and ico in auto_by_ico:
                        target = auto_by_ico[ico]
                        m_type = 'Trùng IČO'
                    elif nname and len(nname) >= 4 and nname in auto_by_name:
                        target = auto_by_name[nname]
                        m_type = 'Trùng Tên chuẩn hóa'

                    if target:
                        w = (row.get(web_col) or '').strip() if web_col else ''
                        m = (row.get(mail_col) or '').strip() if mail_col else ''
                        p = (row.get(phone_col) or '').strip() if phone_col else ''

                        if w or m or p:
                            item = {
                                'source_file': fname,
                                'm_type': m_type,
                                'target_name': target['name'],
                                'target_ico': target['ico'],
                                'src_name': name,
                                'phone': p,
                                'web': w,
                                'email': m
                            }
                            file_matches.append(item)

                            t_key = target['ico'] or target['name']
                            if t_key not in all_matched_entries:
                                all_matched_entries[t_key] = item
                            else:
                                # bổ sung thông tin còn thiếu
                                cur = all_matched_entries[t_key]
                                if not cur['phone'] and p: cur['phone'] = p
                                if not cur['web'] and w: cur['web'] = w
                                if not cur['email'] and m: cur['email'] = m

                if file_matches:
                    count_web = sum(1 for x in file_matches if x['web'])
                    count_mail = sum(1 for x in file_matches if x['email'])
                    count_phone = sum(1 for x in file_matches if x['phone'])
                    print(f"📁 {fname:<30}: Trùng {len(file_matches):>3} cty (Có Web: {count_web:>2}, Có Email: {count_mail:>2}, Có SĐT: {count_phone:>2})")

        except Exception as ex:
            pass

    # 2. Quét các tệp Cache JSON trong crawlmail/
    print("\n" + "=" * 65)
    print("2. KẾT QUẢ ĐỐI CHIẾU TRÊN CÁC BỘ CACHE JSON TRONG CRAWLMAIL/:")
    print("=" * 65)

    json_caches = glob.glob(str(ROOT_DIR / "crawlmail" / "*.json"))
    for jpath in sorted(json_caches):
        jname = os.path.basename(jpath)
        if 'sk_auto' in jname:
            continue

        try:
            with open(jpath, 'r', encoding='utf-8', errors='ignore') as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    continue

                hit = 0
                hit_mail = 0
                hit_web = 0
                hit_phone = 0

                for k, val in data.items():
                    if not isinstance(val, dict):
                        continue
                    c_ico = str(val.get('ico') or '').strip()
                    c_name = str(val.get('name') or val.get('firma') or k).strip()
                    c_nname = norm_name(c_name)

                    target = None
                    if c_ico and c_ico in auto_by_ico:
                        target = auto_by_ico[c_ico]
                    elif c_nname and len(c_nname) >= 4 and c_nname in auto_by_name:
                        target = auto_by_name[c_nname]

                    if target:
                        em = val.get('email') or val.get('emails') or ''
                        wb = val.get('website') or val.get('web') or ''
                        ph = val.get('phone') or ''
                        if em or wb or ph:
                            hit += 1
                            if em: hit_mail += 1
                            if wb: hit_web += 1
                            if ph: hit_phone += 1

                            t_key = target['ico'] or target['name']
                            if t_key not in all_matched_entries:
                                all_matched_entries[t_key] = {
                                    'source_file': jname,
                                    'm_type': 'Cache match',
                                    'target_name': target['name'],
                                    'target_ico': target['ico'],
                                    'phone': ph,
                                    'web': wb,
                                    'email': em
                                }
                            else:
                                cur = all_matched_entries[t_key]
                                if not cur['phone'] and ph: cur['phone'] = ph
                                if not cur['web'] and wb: cur['web'] = wb
                                if not cur['email'] and em: cur['email'] = em

                if hit > 0:
                    print(f"📦 {jname:<35}: Trùng {hit:>3} cty (Có Web: {hit_web:>2}, Có Email: {hit_mail:>2}, Có SĐT: {hit_phone:>2})")

        except Exception as ex:
            pass

    print("\n" + "=" * 65)
    print(f"🎯 TỔNG KẾT DOANH NGHIỆP Ô TÔ TÌM THẤY TRONG CÁC TỆP CÓ SẴN:")
    print("=" * 65)
    unique_with_mail = sum(1 for x in all_matched_entries.values() if x['email'])
    unique_with_web = sum(1 for x in all_matched_entries.values() if x['web'])
    unique_with_phone = sum(1 for x in all_matched_entries.values() if x['phone'])

    print(f"[*] Tổng số doanh nghiệp ô tô trùng khớp: {len(all_matched_entries)} công ty")
    print(f"    - Có Email sẵn sàng nạp: {unique_with_mail} công ty")
    print(f"    - Có Website sẵn sàng:   {unique_with_web} công ty")
    print(f"    - Có SĐT sẵn sàng:       {unique_with_phone} công ty\n")

    print("--- MỘT SỐ CÔNG TY TIÊU BIỂU ĐÃ TÌM THẤY ---")
    count_show = 0
    for key, it in all_matched_entries.items():
        if it['email'] or it['web']:
            print(f"✓ {it['target_name']} (IČO: {it['target_ico']})")
            print(f"  + Nguồn: {it['source_file']} ({it['m_type']})")
            print(f"  + SĐT: {it['phone'] or 'N/A'} | Web: {it['web'] or 'N/A'} | Email: {it['email'] or 'N/A'}")
            count_show += 1
            if count_show >= 15:
                break

    # Save matched info to a seed json file
    seed_path = ROOT_DIR / "crawlmail" / "matched_auto_seed.json"
    with open(seed_path, 'w', encoding='utf-8') as f:
        json.dump(all_matched_entries, f, ensure_ascii=False, indent=2)
    print(f"\n[*] Đã xuất toàn bộ dữ liệu đối chiếu trùng vào: {seed_path.name}")

    # Inject into cache_enrich_maps_sk_auto.json
    cache_path = ROOT_DIR / "crawlmail" / "cache_enrich_maps_sk_auto.json"
    auto_cache = {}
    if cache_path.exists():
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                auto_cache = json.load(f)
        except Exception:
            pass

    injected = 0
    for key, data in all_matched_entries.items():
        ico = data.get('target_ico')
        name = data.get('target_name')
        k = ico if ico else name.lower()

        existing = auto_cache.get(k, {})
        # Update or enrich if current cache has no email
        if not existing.get('email') and data.get('email'):
            auto_cache[k] = {
                'name': name,
                'ico': ico,
                'phone': data.get('phone') or existing.get('phone', ''),
                'website': data.get('web') or existing.get('website', ''),
                'email': data.get('email', ''),
                'updated_at': f"seeded_from_{data.get('source_file')}"
            }
            injected += 1
        elif k not in auto_cache:
            auto_cache[k] = {
                'name': name,
                'ico': ico,
                'phone': data.get('phone', ''),
                'website': data.get('web', ''),
                'email': data.get('email', ''),
                'updated_at': f"seeded_from_{data.get('source_file')}"
            }
            injected += 1

    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(auto_cache, f, ensure_ascii=False, indent=2)

    print(f"[V] Đã nạp thành công {injected} công ty trùng khớp vào bộ Cache làm giàu: {cache_path.name}")
    print(f"    (Tổng số công ty đã được giải quyết sẵn trong Cache: {len(auto_cache):,} công ty)")

    # Sync into SK_AUTO_SLVD_1ENR.csv
    out_file = ROOT_DIR / "SK_AUTO_SLVD_1ENR.csv"
    raw_file = ROOT_DIR / "SK_AUTO_SLVD_0RAW.csv"
    with open(raw_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    with_email = []
    without_email = []

    for r in rows:
        ico = (r.get('IČO') or '').strip()
        cname = (r.get('Công ty') or '').strip().lower()

        cdata = auto_cache.get(ico) or auto_cache.get(cname)
        if cdata:
            if cdata.get('phone') and not r.get('SĐT'):
                p = str(cdata['phone']).strip()
                if p and not p.startswith("'"):
                    p = f"'{p}"
                r['SĐT'] = p
            if cdata.get('website') and not r.get('Web'):
                r['Web'] = cdata['website']
            if cdata.get('email') and not r.get('Email'):
                r['Email'] = cdata['email']

        if r.get('Email'):
            with_email.append(r)
        else:
            without_email.append(r)

    final_rows = with_email + without_email
    for idx, r in enumerate(final_rows, 1):
        r['No.'] = str(idx)

    with open(out_file, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(final_rows)

    print(f"[V] Đã đồng bộ vào {out_file.name}: {len(with_email)} cty có Email đẩy lên đầu bảng!")

if __name__ == "__main__":
    run_cross_check()

