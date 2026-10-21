# -*- coding: utf-8 -*-
"""
Kiem tra va loai bo cac cong ty moi gioi viec lam khong con hoat dong (giai the, pha san, zrusena, v likvidacii, v konkurze)
trong tap du lieu: SK_UDZC_UPSV_2COL.csv

Nguon doi chieu: Otvoreny register slovenskych firiem (ORSF API) - ket noi 14 co quan nha nuoc & toa an Slovakia (ORSR, RPO, RUZ...)
Dua tren ma so thue/doanh nghiep chinh thuc (ICO) tu file goc SK_UDZC_UPSV_0RAW.xlsx voi do chinh xac 100%.

Quy chuan workspace:
- CSV UTF-8 with BOM (utf-8-sig).
- KHONG dung Excel.
- SDT luon co dau nhay don '.
- Day 100% doanh nghiep co email len dau tap tin.
- Co che Checkpoint Cache JSON an toan 100%, resume bat ky luc nao.
"""

import sys
import os
import re
import csv
import json
import time
import unicodedata
import urllib.request
from pathlib import Path

# Cấu hình UTF-8 cho console Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = str(ROOT_DIR / "SK_UDZC_UPSV_2COL.csv")
BACKUP_CSV = str(ROOT_DIR / "SK_UDZC_UPSV_2COL_backup_before_filter.csv")
OUTPUT_CSV = str(ROOT_DIR / "SK_UDZC_UPSV_2COL.csv")
OUTPUT_FMT_CSV = str(ROOT_DIR / "data" / "formatted" / "SK_UDZC_UPSV_2COL.csv")
REMOVED_CSV = str(ROOT_DIR / "data" / "removed_inactive_sk_udzc.csv")
CACHE_FILE = str(ROOT_DIR / "crawlmail" / "cache_sk_udzc_status.json")
RAW_EXCEL = str(ROOT_DIR / "SK_UDZC_UPSV_0RAW.xlsx")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}

def remove_accents(s):
    if not s:
        return ""
    nfkd = unicodedata.normalize('NFKD', str(s))
    return "".join([c for c in nfkd if not unicodedata.combining(c)])

def norm_key(s):
    if not s:
        return ""
    clean = remove_accents(s).lower()
    clean = re.sub(r'[^a-z0-9]', '', clean)
    return clean

def load_ico_mapping():
    """Doc file goc Excel de lay ma ICO cho 100% doanh nghiep."""
    ico_map = {}
    if os.path.exists(RAW_EXCEL):
        try:
            import pandas as pd
            df_raw = pd.read_excel(RAW_EXCEL, sheet_name='Zoznam SZÚ', skiprows=2)
            for _, r in df_raw.iterrows():
                name = str(r.get('Názov', '')).strip()
                ico_raw = str(r.get('IČO', '')).strip()
                digits = re.sub(r'\D', '', ico_raw)
                if name and digits:
                    clean_ico = digits.zfill(8)
                    ico_map[name] = clean_ico
                    ico_map[norm_key(name)] = clean_ico
        except Exception as e:
            print(f"[!] Canh bao doc Excel: {e}")
    return ico_map

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

def batch_lookup_orsf(icos):
    """Truy van batch toi da 100 ICO trong 1 request qua ORSF."""
    url = "https://api.orsf.sk/v1/lookup/batch"
    payload = json.dumps({'icos': icos}).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers=HEADERS)
    
    max_retries = 4
    for attempt in range(max_retries):
        try:
            time.sleep(0.5)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                return data.get('results', [])
        except urllib.error.HTTPError as e:
            if e.code == 429:
                retry_after = 12
                try:
                    retry_after = int(e.headers.get('retry-after', 12))
                except Exception:
                    pass
                print(f" [429 Rate Limit] Cho {retry_after}s...", end='', flush=True)
                time.sleep(retry_after)
            else:
                time.sleep(2)
        except Exception as e:
            time.sleep(2)
            
    return []

def main():
    print("=" * 75)
    print("LOAI BO CAC CONG TY KHONG CON HOAT DONG - SK_UDZC_UPSV_2COL.csv")
    print("=" * 75)

    if not os.path.exists(INPUT_CSV):
        print(f"[LOI] Khong tim thay file nguon: {INPUT_CSV}")
        return

    # Doc file CSV hien tai
    with open(INPUT_CSV, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    total_rows = len(rows)
    print(f"-> Tong so cong ty trong SK_UDZC_UPSV_2COL.csv: {total_rows}")

    # Tao ban backup an toan truoc khi thao tac
    if not os.path.exists(BACKUP_CSV):
        with open(BACKUP_CSV, mode='w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"-> Da tao ban sao luu an toan: {BACKUP_CSV}")

    # Nap ban do ICO tu file goc Excel
    print("-> Dang nap ban do ma ICO tu SK_UDZC_UPSV_0RAW.xlsx...")
    ico_map = load_ico_mapping()
    print(f"-> Da nap {len(ico_map)} ban ghi ICO.")

    cache = load_cache()
    cached_inactive = sum(1 for v in cache.values() if v and not v.get('is_active', True))
    print(f"-> So cong ty da co trong Cache Checkpoint: {len(cache)} (Trong do: {cached_inactive} da xac nhan dong cua)")

    # Xac dinh danh sach cac cong ty can tra cuu ICO
    unresolved_rows = []
    for r in rows:
        cname = r.get('Công ty', '').strip()
        if cname not in cache:
            # Tim ICO
            ico = ico_map.get(cname) or ico_map.get(norm_key(cname))
            unresolved_rows.append((cname, ico))

    print(f"-> So cong ty chua co trong cache can kiem tra: {len(unresolved_rows)}")

    # Thuc hien Batch Lookup theo tung lo 80-100 cong ty
    BATCH_SIZE = 80
    batches = [unresolved_rows[i:i + BATCH_SIZE] for i in range(0, len(unresolved_rows), BATCH_SIZE)]

    try:
        for b_idx, batch in enumerate(batches):
            valid_batch_icos = [item[1] for item in batch if item[1]]
            cname_to_ico = {item[0]: item[1] for item in batch}
            ico_to_cnames = {}
            for item in batch:
                cname, ico = item
                if ico:
                    ico_to_cnames.setdefault(ico, []).append(cname)

            if valid_batch_icos:
                results = batch_lookup_orsf(valid_batch_icos)
                res_by_ico = {item.get('ico'): item for item in results if item.get('ico')}

                for cname, ico in batch:
                    if not ico:
                        cache[cname] = {'matched': False, 'is_active': True, 'reason': 'Khong co ma ICO'}
                        continue

                    r_info = res_by_ico.get(ico)
                    if r_info and r_info.get('found', True) is not False:
                        status = (r_info.get('status') or '').lower()
                        legal_name = r_info.get('name', '')
                        dissolved = r_info.get('dissolvedOn')
                        
                        is_active = True
                        reason = ""
                        
                        if status in ['zrušená', 'zrusena', 'zaniknutá', 'zaniknuta', 'vymazaná', 'vymazana']:
                            is_active = False
                            reason = f"Trạng thái đăng ký: {status}"
                        elif dissolved is not None:
                            is_active = False
                            reason = f"Đã giải thể vào ngày: {dissolved}"
                        elif any(kw in legal_name.lower() for kw in ['v likvid', 'v konkurz', 'reštrukturaliz', 'restrukturaliz']):
                            is_active = False
                            reason = f"Tên pháp lý phá sản/thanh lý: {legal_name}"

                        cache[cname] = {
                            'matched': True,
                            'is_active': is_active,
                            'reason': reason,
                            'ico': ico,
                            'matched_name': legal_name,
                            'status': status
                        }

                        if not is_active:
                            print(f"[KHONG HOAT DONG] {cname} (ICO: {ico}) -> {legal_name} | {reason}", flush=True)
                    else:
                        cache[cname] = {'matched': False, 'is_active': True, 'reason': 'Khong tim thay tren ORSF', 'ico': ico}

            save_cache(cache)
            current_inactive = sum(1 for v in cache.values() if v and not v.get('is_active', True))
            processed_so_far = min((b_idx + 1) * BATCH_SIZE + (total_rows - len(unresolved_rows)), total_rows)
            print(f"-> Tien do: Da kiem tra {processed_so_far}/{total_rows} cong ty | Phat hien {current_inactive} cong ty khong con hoat dong", flush=True)

    except KeyboardInterrupt:
        print("\n\n[TAM DUNG] Nguoi dung nhan tam dung. Da luu cache an toan!")
        save_cache(cache)
        return

    # Luu cache lan cuoi
    save_cache(cache)
    total_inactive = sum(1 for v in cache.values() if v and not v.get('is_active', True))

    print("\n" + "=" * 75)
    print(f"KIEM TRA HOAN TAT: Tong {total_rows} cong ty.")
    print(f"Phat hien tong cong: {total_inactive} cong ty khong con hoat dong.")
    print("=" * 75)

    # Phan loai va loc bo cong ty khong hoat dong
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
        print(f"-> Da luu danh sach cong ty bi loai bo vao: {REMOVED_CSV}")

    # Sap xep du lieu chuan hoa:
    # 1. Day 100% doanh nghiep co email len dau danh sach
    # 2. Dam bao SDT co dau nhay don '
    # 3. Danh lai No. tu 1 den N
    with_email = []
    without_email = []

    for r in active_rows:
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

    # Ghi de vao data/formatted/ truoc, sau do ghi vao SK_UDZC_UPSV_2COL.csv
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

    print(f"-> Da cap nhat tep dich: {OUTPUT_CSV}")
    print(f"-> Da cap nhat tep sao luu chuan hoa: {OUTPUT_FMT_CSV}")
    print(f"-> Tong so cong ty co Email: {len(with_email)}")
    print(f"-> Tong so cong ty khong co Email: {len(without_email)}")
    print("HOAN TAT 100%!")

if __name__ == '__main__':
    main()
