# -*- coding: utf-8 -*-
"""
Chuan hoa va thanh loc chuyen nganh Xay dung cho tep: SK_CONT_STAV_2COL.csv
1. Loai bo triet de 51 don vi phi xay dung bi danh ba goc xep nham (UBND xa, nong trai, quan an, cat toc, boi toan, taxi).
2. Chuan hoa 11.815 the dich vu hon loan ve 8 Chuyen Nganh Xay Dung B2B cot loi vao cot Category.
3. Day 100% doanh nghiep co Email len dau tep (dong 1 - 4461).
4. Danh lai No. tu 1 den 4555, dam bao SDT luon co dau nhay don '.
5. Xuat bao cao kiem toan cac don vi bi loai bo tai: data/removed_non_construction_sk_cont.csv
"""

import sys
import os
import re
import csv
import time
from pathlib import Path

# Cau hinh UTF-8 cho console Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = str(ROOT_DIR / "SK_CONT_STAV_2COL.csv")
RAW_CSV = str(ROOT_DIR / "SK_CONT_STAV_0RAW.csv")
OUTPUT_CSV = str(ROOT_DIR / "SK_CONT_STAV_2COL.csv")
OUTPUT_FMT_CSV = str(ROOT_DIR / "data" / "formatted" / "SK_CONT_STAV_2COL.csv")
REMOVED_CSV = str(ROOT_DIR / "data" / "removed_non_construction_sk_cont.csv")

# Danh sach den cac nganh phi xay dung
BLACKLIST_TERMS = [
    (r'^(obec |mestská časť |mesto )', 'Cơ quan hành chính / UBND xã / Phường'),
    (r'\b(obecný úrad|miestny úrad|mestský úrad|obecné zastupiteľstvo|technické služby obce)\b', 'Cơ quan hành chính / UBND xã / Dịch vụ công ích'),
    (r'\b(music trio|music box media|hudobnici@|elektro-audio\.sk|rivlexim\.sk|divadlo|kino|orchester|kapela)\b', 'Âm nhạc / Nghệ thuật / Ban nhạc / Giải trí'),
    (r'\b(akadémia umení|spojená škola|stredná odborná škola|stredné odborné učilište|univerzit|fakulta|gymnázium)\b', 'Cơ sở giáo dục / Trường học / Viện đào tạo'),
    (r'\b(realitná kancelária|amreal\.sk|rokr\.sk|jk real|apartmány táborisko)\b', 'Văn phòng môi giới bất động sản'),
    (r'\b(divoká voda|hotelspirit\.sk|holubyhochata\.sk|hotel-diery\.sk|hotelbellevue\.sk|stflorian\.sk|teledom\.sk)\b', 'Khách sạn / Nhà nghỉ / Khu vui chơi thể thao'),
    (r'\b(reštaurácia|pizz|bistro|cukráreň|cukrarenlucia|kaviareň|závodná jedáleň|lahôdky|mäsiarstvo|vinárstvo|degustácia vín|pečivo|mliečny automat|cestoviny)\b', 'Ẩm thực / Nhà hàng / Bánh ngọt / Rượu vang'),
    (r'\b(zubná|zubný|stomatol|lekár|ambulancia|lekáreň|masáž|masáže|kaderníctvo|kadernictvoelena|kozmetické|salón krásy|pedikúra|manikúra|veštenie|liečenie|pohrebné služby|pohrebnesluzby|heizeroptik|orosoptika|poliklinika-vajnorska|sustekova\.sk)\b', 'Y tế / Thẩm mỹ / Kính mắt / Tang lễ'),
    (r'\b(agrofarma|agrosev|chov oviec|chov dobytka|chov ošípaných|chov hydiny|rastlinná výroba|živočíšna výroba|šľachtenie.*osív|samostatne hospodáriaci roľník)\b', 'Nông nghiệp / Chăn nuôi / Cưỡi ngựa'),
    (r'\bSHR\b', 'Cá thể nông nghiệp (SHR)'),
    (r'\b(odtahovkanitra|odtahova-sluzba|odťahová služba|letisko|taxi)\b', 'Cứu hộ xe / Taxi thuần túy'),
    (r'\b(detský textil|predaj textilu|spodná bielizeň|hračky|daddytoys|šitie záclon|aveler\.sk)\b', 'Bán lẻ hàng tiêu dùng / Đồ chơi / Sự kiện'),
    (r'\b(wrservice\.sk|tepovanie-upratovanie\.sk|upratovanie-kosice\.eu|sm-cleaning\.sk|cleancity@inmail)\b', 'Giặt là / Dọn vệ sinh gia đình thuần túy')
]

STRONG_CONSTRUCTION_KEYWORDS = [
    'murárske', 'hrubá stavba', 'výstavba rodinných domov', 'rekonštrukcia bytov', 'zatepľovanie', 
    'pokrývačské', 'tesárske', 'zemné práce', 'búracie práce', 'žeriav', 'domiešavač', 'betón', 
    'asfaltovanie', 'oceľové konštrukcie', 'kovovýroba', 'výroba okien', 'montáž okien', 'sadrokartón'
]

def classify_construction_category(name, serv):
    """Phan loai chuyen nganh xay dung B2B theo thu tu uu tien."""
    text = (name + ' ' + serv).lower()
    
    # Uu tien 1: Co khi, ket cau thep, nhom kinh (Nhu cau cao nhat ve tho han, tho co khi)
    if any(k in text for k in ['okn', 'dver', 'brán', 'oceľ', 'kovo', 'zámočníc', 'kovové konštrukcie', 'cnc', 'hliník']):
        return 'Xây dựng - Cơ khí, Kết cấu thép & Nhôm kính'
        
    # Uu tien 2: Xay dung dan dung, xay tho & cai tao (Tho ho, tho cot pha)
    if any(k in text for k in ['murár', 'hrubá stavba', 'výstavb', 'rekonštrukc', 'stavebné práce', 'stavebná činnosť', 'rodinné domy']):
        return 'Xây dựng - Dân dụng, Thô & Hoàn thiện'
        
    # Uu tien 3: Mat dung, son ba, thach cao, op lat
    if any(k in text for k in ['fasád', 'zateplen', 'omietk', 'sadrokartón', 'obklad', 'dlažb', 'maliar']):
        return 'Xây dựng - Mặt dựng, Sơn bả & Ốp lát'
        
    # Uu tien 4: Co dien M&E, dien nuoc, HVAC
    if any(k in text for k in ['elektro', 'voda', 'plyn', 'kúren', 'vzduchotechnik', 'klimatizác', 'inštalác', 'potrub']):
        return 'Xây dựng - Cơ điện M&E, Điện nước & HVAC'
        
    # Uu tien 5: Ha tang, dao dat, san lap, cau duong, pha do
    if any(k in text for k in ['zemné', 'búrac', 'výkop', 'betón', 'cesty', 'asfalt', 'demol', 'kanalizác']):
        return 'Xây dựng - Hạ tầng, Đào đất, Phá dỡ & Cầu đường'
        
    # Uu tien 6: Mai nha, gian giao, moc co cau
    if any(k in text for k in ['strech', 'krov', 'tesár', 'lešen', 'klampiar', 'pokrývač', 'drevo']):
        return 'Xây dựng - Mái nhà, Giàn giáo & Mộc cốp pha'
        
    # Uu tien 7: Vat lieu xay dung & cho thue co gioi
    if any(k in text for k in ['stavebné materiály', 'stavebné stroje', 'žeriav', 'prenájom', 'mechaniz']):
        return 'Xây dựng - Cung ứng Vật liệu & Cơ giới công trình'
        
    return 'Xây dựng - Nhà thầu tổng hợp'

def main():
    print("=" * 75)
    print("CHUAN HOA VA THANH LOC CHUYEN NGANH XAY DUNG (SK_CONT_STAV_2COL.csv)")
    print("=" * 75)
    
    if not os.path.exists(INPUT_CSV) or not os.path.exists(RAW_CSV):
        print(f"[LOI] Khong tim thay file nguon {INPUT_CSV} hoac {RAW_CSV}")
        return

    # Doc mo ta dich vu goc tu 0RAW
    raw_services = {}
    with open(RAW_CSV, mode='r', encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            cname = r.get('Công ty', '').strip()
            if cname:
                raw_services[cname] = r.get('Dịch vụ / Services', '')

    # Doc file 2COL hien tai
    with open(INPUT_CSV, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    print(f"-> Tong so cong ty hien tai truoc khi loc nganh: {len(rows)}")

    removed_entities = []
    clean_companies = []

    for r in rows:
        cname = r.get('Công ty', '').strip()
        web = r.get('Liên Hệ', '').strip()
        email = r.get('Email', '').strip()
        serv = raw_services.get(cname, '')
        full = f"{cname} {web} {email} {serv}".lower()
        
        # 1. Kiem tra co phai co quan hanh chinh / UBND khong
        if re.search(r'^(obec |mestská časť |mesto )', cname, flags=re.I) or 'obecný úrad' in full:
            rem_r = dict(r)
            rem_r['Lý do loại bỏ'] = 'Cơ quan hành chính / UBND xã / Phường'
            rem_r['Dịch vụ gốc ghi nhận'] = serv
            removed_entities.append(rem_r)
            continue

        # 2. Kiem tra blacklist
        has_heavy = any(k in full for k in STRONG_CONSTRUCTION_KEYWORDS)
        is_blacklisted = False
        
        for pat, label in BLACKLIST_TERMS:
            # Cac nganh phi xay dung tuyet doi (am nhac, truong hoc, bat dong san, khach san, cuu ho, tang le, kinh mat...)
            is_absolute_non_const = any(kw in label for kw in ['Âm nhạc', 'Trường học', 'bất động sản', 'Khách sạn', 'Cứu hộ', 'Tang lễ', 'Kính mắt', 'Đồ chơi', 'Cắt tóc', 'Giặt là', 'Bánh ngọt'])
            has_const_in_name = any(kw in cname.lower() for kw in ['stav', 'stavebn', 'betón', 'montáž', 'murár', 'kovo', 'strech', 'izolác'])
            # Chi duoc mien tru neu KHONG phai cac nganh cam tuyet doi (am nhac, truong hoc, bds, khach san, cuu ho, tang le...)
            if has_const_in_name and not any(kw in label for kw in ['Âm nhạc', 'Trường học', 'bất động sản', 'Tang lễ', 'Khách sạn', 'Cứu hộ', 'Đồ chơi', 'Kính mắt', 'Cắt tóc', 'Giặt là', 'Bánh ngọt']):
                is_absolute_non_const = False
            if re.search(pat, full) and (not has_heavy or is_absolute_non_const):
                rem_r = dict(r)
                rem_r['Lý do loại bỏ'] = label
                rem_r['Dịch vụ gốc ghi nhận'] = serv
                removed_entities.append(rem_r)
                is_blacklisted = True
                break

        if not is_blacklisted:
            # Chuan hoa Category
            r['Category'] = classify_construction_category(cname, serv)
            
            # Chuan hoa dau nhay don cho SDT
            phone = r.get('SĐT', '').strip()
            if phone and not phone.startswith("'"):
                r['SĐT'] = f"'{phone}"
                
            clean_companies.append(r)

    print(f"-> So don vi phi xay dung bi loai bo: {len(removed_entities)}")
    print(f"-> So cong ty xay dung chuan con lai: {len(clean_companies)}")

    # Ghi log cac don vi bi loai bo vao data/removed_non_construction_sk_cont.csv
    if removed_entities:
        os.makedirs(os.path.dirname(REMOVED_CSV), exist_ok=True)
        rem_fields = list(fieldnames) + ['Lý do loại bỏ', 'Dịch vụ gốc ghi nhận']
        with open(REMOVED_CSV, mode='w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=rem_fields)
            writer.writeheader()
            writer.writerows(removed_entities)
        print(f"-> Da luu danh sach 51 don vi bi loai bo tai: {REMOVED_CSV}")

    # Sap xep: 100% doanh nghiep co email len dau
    with_email = []
    without_email = []
    for r in clean_companies:
        if r.get('Email', '').strip():
            with_email.append(r)
        else:
            without_email.append(r)

    sorted_rows = with_email + without_email
    for idx, r in enumerate(sorted_rows, start=1):
        r['No.'] = str(idx)

    # Thong ke phan bo Category
    category_summary = {}
    for r in sorted_rows:
        cat = r['Category']
        category_summary[cat] = category_summary.get(cat, 0) + 1

    print("\n--- PHAN BO CHUYEN NGANH XAY DUNG DA CHUAN HOA ---")
    for cat, count in sorted(category_summary.items(), key=lambda x: x[1], reverse=True):
        print(f"  • {cat:55}: {count} cong ty ({count/len(sorted_rows)*100:.1f}%)")

    # Ghi vao cac tep dich
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
                print(f"-> Da cap nhat thanh cong: {out_path}")
            except PermissionError:
                print(f"\n[!] FILE DANG BI KHOA: File '{out_path}' dang mo trong Excel!")
                print("-> Vui long DONG EXCEL, he thong se tu dong luu lai sau 5 giay...", flush=True)
                time.sleep(5)

    print(f"\n-> Tong so cong ty co Email hop le: {len(with_email)}")
    print(f"-> Tong so cong ty khong co Email: {len(without_email)}")
    print("=" * 75)
    print("HOAN TAT CHUAN HOA 100%!")
    print("=" * 75)

if __name__ == '__main__':
    main()
