# -*- coding: utf-8 -*-
"""
Kiem tra va loai bo cac cong ty khong con hoat dong (giai the, pha san, zrusena, v likvidacii, v konkurze)
trong tap du lieu nganh Xay dung Slovakia: SK_CONT_STAV_2COL.csv

Nguon doi chieu: Otvoreny register slovenskych firiem (ORSF API) - tong hop 14 so bo nganh & toa an Slovakia (ORSR, RPO, RUZ...)
Quy chuan workspace:
- CSV UTF-8 with BOM (utf-8-sig).
- KHONG dung Excel.
- SDT luon co dau nhay don '.
- Day 100% doanh nghiep co email len dau tap tin.
- Co che Checkpoint Cache JSON an toan 100%, chay ngat ket noi van tiep tuc duoc.
"""

import sys
import os
import re
import csv
import json
import time
import unicodedata
import urllib.request
import urllib.parse
from pathlib import Path

# Cấu hình UTF-8 cho console Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = str(ROOT_DIR / "SK_CONT_STAV_2COL.csv")
BACKUP_CSV = str(ROOT_DIR / "SK_CONT_STAV_2COL_backup_before_filter.csv")
OUTPUT_CSV = str(ROOT_DIR / "SK_CONT_STAV_2COL.csv")
OUTPUT_FMT_CSV = str(ROOT_DIR / "data" / "formatted" / "SK_CONT_STAV_2COL.csv")
REMOVED_CSV = str(ROOT_DIR / "data" / "removed_inactive_sk_cont.csv")
CACHE_FILE = str(ROOT_DIR / "crawlmail" / "cache_sk_cont_status.json")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json'
}

def remove_accents(input_str):
    if not input_str:
        return ""
    nfkd = unicodedata.normalize('NFKD', str(input_str))
    return "".join([c for c in nfkd if not unicodedata.combining(c)])

def clean_company_name(name):
    clean = re.sub(r'["\']', '', name)
    clean = re.sub(r'\s*(?:spol\.\s*s\s*r\.?\s*o\.?|s\.?\s*r\.?\s*o\.?|a\.?\s*s\.?|k\.?\s*s\.?|v\.?\s*o\.?\s*s\.?|d\.?d\.?)\s*$', '', clean, flags=re.I)
    return clean.strip()

def extract_city(address):
    if not address:
        return ""
    m = re.search(r'\d{3}\s*\d{2}\s+([A-Za-zÀ-ž\s\-]+?)(?:,|$)', address)
    if m:
        return m.group(1).strip()
    return ""

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] Khong the luu cache: {e}")

def check_company_orsf(company_name, city):
    q_name = clean_company_name(company_name)
    if not q_name:
        return None
    
    url = f"https://api.orsf.sk/v1/search?q={urllib.parse.quote(q_name)}"
    req = urllib.request.Request(url, headers=HEADERS)
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            time.sleep(0.35)
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                hits = data.get('hits', [])
                
                matched = None
                norm_cname = remove_accents(q_name).lower()
                norm_city = remove_accents(city).lower()
                
                for h in hits:
                    h_name = h.get('name', '')
                    h_clean = remove_accents(clean_company_name(h_name)).lower()
                    h_city = remove_accents(h.get('city', '')).lower()
                    
                    # So khop ten chinh xac hoac ten chua va cung thanh pho
                    if norm_cname == h_clean:
                        matched = h
                        break
                    elif norm_city and norm_city == h_city and (norm_cname in h_clean or h_clean in norm_cname):
                        matched = h
                        break
                
                if matched:
                    status = (matched.get('status') or '').lower()
                    h_name = matched.get('name', '')
                    ico = matched.get('ico', '')
                    dissolved = matched.get('dissolvedOn')
                    
                    is_active = True
                    reason = ""
                    
                    # Danh gia tinh trang phap ly
                    if status in ['zrušená', 'zrusena', 'zaniknutá', 'zaniknuta', 'vymazaná', 'vymazana']:
                        is_active = False
                        reason = f"Trạng thái đăng ký: {status}"
                    elif dissolved is not None:
                        is_active = False
                        reason = f"Đã giải thể vào ngày: {dissolved}"
                    elif any(kw in h_name.lower() for kw in ['v likvid', 'v konkurz', 'reštrukturaliz', 'restrukturaliz']):
                        is_active = False
                        reason = f"Tên pháp lý phá sản/giải thể: {h_name}"
                    
                    return {
                        'matched': True,
                        'is_active': is_active,
                        'reason': reason,
                        'ico': ico,
                        'matched_name': h_name,
                        'status': status
                    }
                else:
                    return {'matched': False, 'is_active': True, 'reason': 'Khong tim thay tren ORSF'}
                    
        except urllib.error.HTTPError as e:
            if e.code == 429:
                retry_after = 10
                try:
                    retry_after = int(e.headers.get('retry-after', 10))
                except Exception:
                    pass
                print(f" [429 Rate Limit] Cho {retry_after}s...", end='', flush=True)
                time.sleep(retry_after)
            else:
                time.sleep(1)
        except Exception as e:
            time.sleep(1.5)
            
    return None

def main():
    print("=" * 70)
    print("LOAI BO CAC CONG TY KHONG CON HOAT DONG (SK_CONT_STAV_2COL.csv)")
    print("=" * 70)
    
    if not os.path.exists(INPUT_CSV):
        print(f"[LOI] Khong tim thay tep nguon: {INPUT_CSV}")
        return

    # Doc toan bo file CSV
    with open(INPUT_CSV, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    total_rows = len(rows)
    print(f"-> Tong so cong ty can kiem tra: {total_rows}")

    # Tao ban backup truoc khi loc
    if not os.path.exists(BACKUP_CSV):
        with open(BACKUP_CSV, mode='w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"-> Da tao ban sao luu an toan: {BACKUP_CSV}")

    cache = load_cache()
    cached_inactive = sum(1 for v in cache.values() if v and not v.get('is_active', True))
    print(f"-> So cong ty da co trong Cache Checkpoint: {len(cache)} (Trong do: {cached_inactive} da xac nhan dong cua)")
    if len(cache) > 0 and len(cache) < total_rows:
        print(f"-> Tiep tuc quet ngay tu vi tri #{len(cache) + 1}/{total_rows}...\n", flush=True)

    # Bat dau kiem tra tung cong ty
    inactive_count = cached_inactive
    checked_count = 0
    
    try:
        for idx, r in enumerate(rows):
            cname = r.get('Công ty', '').strip()
            address = r.get('Địa chỉ', '').strip()
            city = extract_city(address)
            
            is_new = False
            if cname in cache and cache[cname] is not None:
                res = cache[cname]
            else:
                is_new = True
                res = check_company_orsf(cname, city)
                if res is not None:
                    cache[cname] = res
                else:
                    cache[cname] = {'matched': False, 'is_active': True, 'reason': 'Loi ket noi tam thoi'}
                    
                checked_count += 1
                if checked_count % 5 == 0:
                    save_cache(cache)
                    
            if is_new:
                if res and not res.get('is_active', True):
                    inactive_count += 1
                    print(f"[{idx+1}/{total_rows}] [KHONG HOAT DONG] {cname} -> {res.get('matched_name')} | {res.get('reason')}", flush=True)
                else:
                    if checked_count % 10 == 0 or checked_count < 5:
                        print(f"[{idx+1}/{total_rows}] Tien do: Da quet {len(cache)}/{total_rows} cong ty | Phat hien {inactive_count} khong hoat dong", flush=True)
                        
    except KeyboardInterrupt:
        print("\n\n[TAM DUNG] Nguoi dung nhan dung tien trinh. Dang luu cache an toan...")
        save_cache(cache)
        print(f"[CACHE AN TOAN] Da luu checkpoint {len(cache)}/{total_rows} cong ty vao cache. Ban co the chay lai bat ky luc nao de tiep tuc!")
        return

    # Luu cache lan cuoi
    save_cache(cache)
    print("\n" + "=" * 70)
    print(f"KIEM TRA HOAN TAT: Tong cong {total_rows} cong ty.")
    print(f"So cong ty khong con hoat dong phat hien: {inactive_count}")
    print("=" * 70)

    # Phan loai va loc du lieu
    active_rows = []
    removed_rows = []
    
    for r in rows:
        cname = r.get('Công ty', '').strip()
        info = cache.get(cname, {})
        if info.get('is_active', True):
            active_rows.append(r)
        else:
            removed_r = dict(r)
            removed_r['IČO'] = info.get('ico', '')
            removed_r['Lý do loại bỏ'] = info.get('reason', '')
            removed_r['Tên pháp lý ghi nhận'] = info.get('matched_name', '')
            removed_rows.append(removed_r)

    print(f"-> So luong cong ty hop le giu lai: {len(active_rows)}")
    print(f"-> So luong cong ty da bi loai bo: {len(removed_rows)}")

    # Ghi log danh sach cong ty da loai bo
    if removed_rows:
        os.makedirs(os.path.dirname(REMOVED_CSV), exist_ok=True)
        rem_fields = list(fieldnames) + ['IČO', 'Lý do loại bỏ', 'Tên pháp lý ghi nhận']
        with open(REMOVED_CSV, mode='w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=rem_fields)
            writer.writeheader()
            writer.writerows(removed_rows)
        print(f"-> Da luu danh sach cong ty bi xoa vao: {REMOVED_CSV}")

    # Sap xep du lieu chuan hoa:
    # 1. Day 100% doanh nghiep co email len dau
    # 2. Dam bao SDT co nhay don '
    # 3. Danh lai No. tu 1 den N
    with_email = []
    without_email = []
    
    for r in active_rows:
        # Chuan hoa SDT
        phone = r.get('SĐT', '').strip()
        if phone and not phone.startswith("'"):
            r['SĐT'] = f"'{phone}"
            
        email = r.get('Email', '').strip()
        if email:
            with_email.append(r)
        else:
            without_email.append(r)

    sorted_rows = with_email + without_email
    for i, r in enumerate(sorted_rows, start=1):
        r['No.'] = str(i)

    # Ghi vao data/formatted/ truoc, sau do ghi vao SK_CONT_STAV_2COL.csv
    for out_path in [OUTPUT_FMT_CSV, OUTPUT_CSV]:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        written = False
        while not written:
            try:
                with open(out_path, mode='w', encoding='utf-8-sig', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(sorted_rows)
                written = True
                print(f"-> Da cap nhat tep: {out_path}")
            except PermissionError:
                print(f"\n[!] FILE DANG BI KHOA: File '{out_path}' dang duoc mo boi Excel hoac phan mem khac!")
                print("-> Vui long DONG / TAT CUA SO EXCEL dang mo file nay. He thong se tu dong thu luu lai sau 5 giay...", flush=True)
                time.sleep(5)

    print(f"-> Tong so cong ty co Email: {len(with_email)}")
    print(f"-> Tong so cong ty khong co Email: {len(without_email)}")
    print("HOAN TAT 100%!")

if __name__ == '__main__':
    main()
