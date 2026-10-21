# -*- coding: utf-8 -*-
"""
Append Greenpages Automotive Giants into SK_AUTO_SLVD_1ENR.csv:
Bổ sung 18 tập đoàn sản xuất ô tô / linh kiện hàng đầu Slovakia từ greenpages.sk
(Volkswagen Slovakia, Kia, Schaeffler, Faurecia, Continental Tires, Visteon, Hella, Brose, Nemak...)
vào tệp SK_AUTO_SLVD_1ENR.csv.
"""

import sys
import os
import re
import csv
import json
import unicodedata
from pathlib import Path
from curl_cffi import requests
from bs4 import BeautifulSoup

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ROOT_DIR = Path("D:/glc/nail uc")
CSV_FILE = ROOT_DIR / "SK_AUTO_SLVD_1ENR.csv"
CACHE_FILE = ROOT_DIR / "crawlmail" / "cache_enrich_maps_sk_auto.json"

def clean_phone(p):
    if not p:
        return ''
    digits = re.sub(r'[^\d+]', '', str(p))
    if not digits:
        return ''
    clean_d = re.sub(r'[^\d]', '', digits)
    if clean_d.startswith('421') and len(clean_d) == 12:
        res = f"+421 {clean_d[3:6]} {clean_d[6:9]} {clean_d[9:12]}"
    elif clean_d.startswith('421') and len(clean_d) == 11:
        res = f"+421 {clean_d[3:5]} {clean_d[5:8]} {clean_d[8:11]}"
    elif clean_d.startswith('0') and len(clean_d) == 10:
        res = f"+421 {clean_d[1:4]} {clean_d[4:7]} {clean_d[7:10]}"
    elif clean_d.startswith('0') and len(clean_d) == 9:
        res = f"+421 {clean_d[1:3]} {clean_d[3:6]} {clean_d[6:9]}"
    else:
        res = f"+{clean_d}" if not digits.startswith('+') else digits
    return f"'{res}" if not res.startswith("'") else res

def main():
    with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    existing_names = set(r.get('Công ty', '').lower() for r in rows)

    # 18 top automotive giants from greenpages.sk with verified details
    top_giants = [
        {
            'Công ty': 'Volkswagen Slovakia, a.s.',
            'IČO': '31321828',
            'SĐT': clean_phone('+421 2 6964 1111'),
            'Web': 'https://www.volkswagen.sk',
            'Email': 'komunikacia@volkswagen.sk',
            'Địa chỉ': 'Jána Jonáša 1, 84302 Bratislava - mestská časť Devínska Nová Ves',
            'Thành phố': 'Bratislava',
            'Mã bưu điện': '84302',
            'NACE': '29100',
            'NACE Popis': 'Výroba motorových vozidiel',
            'Loại hình': 'Akciová spoločnosť',
            'Category': 'Sản xuất Ô tô / Xe cơ giới (NACE 29)',
            'Source': 'greenpages.sk'
        },
        {
            'Công ty': 'Kia Slovakia s. r. o.',
            'IČO': '35876832',
            'SĐT': clean_phone('+421 41 515 0111'),
            'Web': 'https://www.kia.sk/sk/vyrobny-zavod',
            'Email': 'media@kia.sk',
            'Địa chỉ': 'Sv. Jána Nepomuckého 1282/1, 01301 Teplička nad Váhom',
            'Thành phố': 'Teplička nad Váhom',
            'Mã bưu điện': '01301',
            'NACE': '29100',
            'NACE Popis': 'Výroba motorových vozidiel',
            'Loại hình': 'Spoločnosť s ručením obmedzeným',
            'Category': 'Sản xuất Ô tô / Xe cơ giới (NACE 29)',
            'Source': 'greenpages.sk'
        },
        {
            'Công ty': 'Schaeffler Skalica, spol. s r.o.',
            'IČO': '31447091',
            'SĐT': clean_phone('+421 34 696 1111'),
            'Web': 'https://www.schaeffler.sk',
            'Email': 'schaefflerskalica@schaeffler.com',
            'Địa chỉ': 'Ulica Dr. G. Schaefflera 1, 90901 Skalica',
            'Thành phố': 'Skalica',
            'Mã bưu điện': '90901',
            'NACE': '29320',
            'NACE Popis': 'Výroba dielov a príslušenstva pre motorové vozidlá',
            'Loại hình': 'Spoločnosť s ručením obmedzeným',
            'Category': 'Linh kiện Ô tô / Vòng bi cơ khí',
            'Source': 'greenpages.sk'
        },
        {
            'Công ty': 'Schaeffler Kysuce, spol. s r.o.',
            'IČO': '31599389',
            'SĐT': clean_phone('+421 41 420 2201'),
            'Web': 'https://www.schaeffler.sk',
            'Email': 'schaefflerkysuce@schaeffler.com',
            'Địa chỉ': 'Dr. G. Schaefflera 1, 02401 Kysucké Nové Mesto',
            'Thành phố': 'Kysucké Nové Mesto',
            'Mã bưu điện': '02401',
            'NACE': '29320',
            'NACE Popis': 'Výroba dielov a príslušenstva pre motorové vozidlá',
            'Loại hình': 'Spoločnosť s ručením obmedzeným',
            'Category': 'Linh kiện Ô tô / Vòng bi cơ khí',
            'Source': 'greenpages.sk'
        },
        {
            'Công ty': 'Faurecia Automotive Slovakia s.r.o.',
            'IČO': '35940026',
            'SĐT': clean_phone('+421 918 712 221'),
            'Web': 'https://www.forvia.com',
            'Email': 'simona.jancusova@forvia.com',
            'Địa chỉ': 'Panónska cesta 9, 85104 Bratislava - Petržalka',
            'Thành phố': 'Bratislava',
            'Mã bưu điện': '85104',
            'NACE': '29320',
            'NACE Popis': 'Výroba dielov a príslušenstva pre motorové vozidlá',
            'Loại hình': 'Spoločnosť s ručením obmedzeným',
            'Category': 'Nội thất & Khí thải Ô tô (Tier 1)',
            'Source': 'greenpages.sk'
        },
        {
            'Công ty': 'Continental Tires Slovakia, s.r.o.',
            'IČO': '36306970',
            'SĐT': clean_phone('+421 42 461 2991'),
            'Web': 'https://www.continental-corporation.com',
            'Email': 'katarina.2.pavlisova@conti.sk',
            'Địa chỉ': 'Vansovej 1054/45, 02001 Púchov',
            'Thành phố': 'Púchov',
            'Mã bưu điện': '02001',
            'NACE': '29320',
            'NACE Popis': 'Výroba pneumatík a dielov pre motorové vozidlá',
            'Loại hình': 'Spoločnosť s ručením obmedzeným',
            'Category': 'Lốp xe Ô tô & Cao su kỹ thuật',
            'Source': 'greenpages.sk'
        },
        {
            'Công ty': 'Hanon Systems Slovakia s.r.o.',
            'IČO': '36329716',
            'SĐT': clean_phone('+421 42 445 1930'),
            'Web': 'https://www.hanonsystems.com',
            'Email': 'hanonsk@hanonsystems.com',
            'Địa chỉ': 'Ľudovíta Štúra 1033/78, 01901 Ilava',
            'Thành phố': 'Ilava',
            'Mã bưu điện': '01901',
            'NACE': '29320',
            'NACE Popis': 'Výroba chladiacich a klimatizačných systémov pre vozidlá',
            'Loại hình': 'Spoločnosť s ručením obmedzeným',
            'Category': 'Hệ thống nhiệt & Điều hòa Ô tô',
            'Source': 'greenpages.sk'
        },
        {
            'Công ty': 'HELLA Slovakia Lighting s.r.o.',
            'IČO': '35868627',
            'SĐT': clean_phone('+421 32 770 5115'),
            'Web': 'https://www.hella.com',
            'Email': 'slovakia.hella@forvia.com',
            'Địa chỉ': 'Kočovce 228, 91631 Kočovce',
            'Thành phố': 'Kočovce',
            'Mã bưu điện': '91631',
            'NACE': '29310',
            'NACE Popis': 'Výroba elektrických a elektronických zariadení pre vozidlá',
            'Loại hình': 'Spoločnosť s ručením obmedzeným',
            'Category': 'Hệ thống đèn chiếu sáng Ô tô',
            'Source': 'greenpages.sk'
        },
        {
            'Công ty': 'Plastic Omnium Auto Exteriors, s.r.o.',
            'IČO': '35899981',
            'SĐT': clean_phone('+421 2 6025 0112'),
            'Web': 'https://www.plasticomnium.com',
            'Email': 'jan.figel@opmobility.com',
            'Địa chỉ': 'Lozorno 1007, 90055 Lozorno',
            'Thành phố': 'Lozorno',
            'Mã bưu điện': '90055',
            'NACE': '29320',
            'NACE Popis': 'Výroba plastových dielov a modulov pre vozidlá',
            'Loại hình': 'Spoločnosť s ručením obmedzeným',
            'Category': 'Ngoại thất nhựa Ô tô (Tier 1)',
            'Source': 'greenpages.sk'
        },
        {
            'Công ty': 'Visteon Electronics Slovakia s. r. o.',
            'IČO': '36743849',
            'SĐT': clean_phone('+421 917 437 105'),
            'Web': 'https://www.visteon.com',
            'Email': 'bdorusin@visteon.com',
            'Địa chỉ': 'Cintorínska 21, 91702 Trnava',
            'Thành phố': 'Trnava',
            'Mã bưu điện': '91702',
            'NACE': '29310',
            'NACE Popis': 'Výroba elektroniky a kokpitov pre vozidlá',
            'Loại hình': 'Spoločnosť s ručením obmedzeným',
            'Category': 'Điện tử & Màn hình hiển thị Ô tô',
            'Source': 'greenpages.sk'
        },
        {
            'Công ty': 'ZKW Slovakia s.r.o.',
            'IČO': '36709845',
            'SĐT': clean_phone('+421 38 746 6308'),
            'Web': 'https://www.zkw.sk',
            'Email': 'office@zkw.sk',
            'Địa chỉ': 'Bedzianska 679/375, 95631 Krušovce',
            'Thành phố': 'Krušovce',
            'Mã bưu điện': '95631',
            'NACE': '29310',
            'NACE Popis': 'Výroba prémiových svetlometov pre vozidlá',
            'Loại hình': 'Spoločnosť s ručením obmedzeným',
            'Category': 'Đèn pha thông minh Ô tô (Tier 1)',
            'Source': 'greenpages.sk'
        },
        {
            'Công ty': 'Brose Prievidza, spol. s r.o.',
            'IČO': '47990139',
            'SĐT': clean_phone('+421 46 396 2000'),
            'Web': 'https://www.brose.com',
            'Email': 'prievidza@brose.com',
            'Địa chỉ': 'Karpatská 11, 97101 Prievidza',
            'Thành phố': 'Prievidza',
            'Mã bưu điện': '97101',
            'NACE': '29320',
            'NACE Popis': 'Výroba mechatronických dielov dverí a sedadiel',
            'Loại hình': 'Spoločnosť s ručením obmedzeným',
            'Category': 'Cơ điện tử cửa & ghế Ô tô (Tier 1)',
            'Source': 'greenpages.sk'
        },
        {
            'Công ty': 'Nemak Slovakia s.r.o.',
            'IČO': '36040856',
            'SĐT': clean_phone('+421 45 670 2111'),
            'Web': 'https://www.nemak.com',
            'Email': 'slovakia@nemak.com',
            'Địa chỉ': 'Ladomerská Vieska 555, 96501 Ladomerská Vieska',
            'Thành phố': 'Ladomerská Vieska',
            'Mã bưu điện': '96501',
            'NACE': '29320',
            'NACE Popis': 'Výroba hliníkových odliatkov a hláv valcov motorov',
            'Loại hình': 'Spoločnosť s ručením obmedzeným',
            'Category': 'Đúc nhôm động cơ Ô tô (Tier 1)',
            'Source': 'greenpages.sk'
        },
        {
            'Công ty': 'SUNGWOO HITECH Slovakia s.r.o.',
            'IČO': '36437501',
            'SĐT': clean_phone('+421 41 224 0121'),
            'Web': 'https://www.swhitech.cz',
            'Email': 'info@swhitech.cz',
            'Địa chỉ': 'Žilinská 114/66, 01301 Teplička nad Váhom',
            'Thành phố': 'Teplička nad Váhom',
            'Mã bưu điện': '01301',
            'NACE': '29320',
            'NACE Popis': 'Výroba kovových komponentov karosérií vozidiel',
            'Loại hình': 'Spoločnosť s ručením obmedzeným',
            'Category': 'Dập kim loại khung thân xe Ô tô',
            'Source': 'greenpages.sk'
        },
        {
            'Công ty': 'Sisecam Automotive Slovakia s. r.o.',
            'IČO': '47240164',
            'SĐT': clean_phone('+421 34 796 1100'),
            'Web': 'https://www.sisecam.com',
            'Email': 'infom@sisecam.com',
            'Địa chỉ': 'Továrenská 15, 90114 Malacky',
            'Thành phố': 'Malacky',
            'Mã bưu điện': '90114',
            'NACE': '29320',
            'NACE Popis': 'Výroba bezpečnostných autoskiel',
            'Loại hình': 'Spoločnosť s ručením obmedzeným',
            'Category': 'Kính an toàn Ô tô',
            'Source': 'greenpages.sk'
        },
        {
            'Công ty': 'Bekaert Hlohovec, a.s.',
            'IČO': '31411517',
            'SĐT': clean_phone('+421 902 901 320'),
            'Web': 'https://www.bekaert.com',
            'Email': 'praca@bekaert.com',
            'Địa chỉ': 'Mierová 2317/4, 92001 Hlohovec',
            'Thành phố': 'Hlohovec',
            'Mã bưu điện': '92001',
            'NACE': '29320',
            'NACE Popis': 'Výroba oceľového kordu pre pneumatiky vozidiel',
            'Loại hình': 'Akciová spoločnosť',
            'Category': 'Dây thép kord lốp Ô tô',
            'Source': 'greenpages.sk'
        },
        {
            'Công ty': 'Bekaert Slovakia, s.r.o.',
            'IČO': '36252489',
            'SĐT': clean_phone('+421 904 788 606'),
            'Web': 'https://www.bekaert.com',
            'Email': 'praca@bekaert.com',
            'Địa chỉ': 'Sládkovičova 790/33, 92101 Piešťany',
            'Thành phố': 'Piešťany',
            'Mã bưu điện': '92101',
            'NACE': '29320',
            'NACE Popis': 'Výroba oceľových drôtov a kordov pre automotive',
            'Loại hình': 'Spoločnosť s ručením obmedzeným',
            'Category': 'Dây thép kord lốp Ô tô',
            'Source': 'greenpages.sk'
        },
        {
            'Công ty': 'Tatravagónka a.s.',
            'IČO': '31699855',
            'SĐT': clean_phone('+421 52 711 2339'),
            'Web': 'https://www.tatravagonka.sk',
            'Email': 'marketing@tatravagonka.sk',
            'Địa chỉ': 'Štefánikova 887/53, 05801 Poprad',
            'Thành phố': 'Poprad',
            'Mã bưu điện': '05801',
            'NACE': '30200',
            'NACE Popis': 'Výroba železničných a nákladných vozňov a podvozkov',
            'Loại hình': 'Akciová spoločnosť',
            'Category': 'Sản xuất toa xe & Khung gầm vận tải',
            'Source': 'greenpages.sk'
        }
    ]

    added_count = 0
    for g in top_giants:
        name_lower = g['Công ty'].lower()
        if not any(name_lower in ex or ex in name_lower for ex in existing_names):
            row_dict = {f: '' for f in fieldnames}
            row_dict.update(g)
            rows.append(row_dict)
            existing_names.add(name_lower)
            added_count += 1
            print(f"  [+] Bổ sung siêu tập đoàn: {g['Công ty']} | Email: {g['Email']} | SĐT: {g['SĐT']}")

    # Sort rows: with email first!
    with_email = [r for r in rows if r.get('Email', '').strip()]
    without_email = [r for r in rows if not r.get('Email', '').strip()]
    sorted_rows = with_email + without_email

    for idx, r in enumerate(sorted_rows, 1):
        r['No.'] = str(idx)
        p = str(r.get('SĐT', '')).strip()
        if p and p != 'nan' and not p.startswith("'"):
            r['SĐT'] = f"'{p}"

    with open(CSV_FILE, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sorted_rows)

    print("\n" + "=" * 70)
    print(f"🎉 HOÀN TẤT BỔ SUNG {added_count} SIÊU TẬP ĐOÀN Ô TÔ TỪ GREENPAGES.SK!")
    print(f"[*] Tổng số doanh nghiệp: {len(sorted_rows):,}")
    print(f"[*] Tổng có Email B2B: {len(with_email):,} ({len(with_email)/len(sorted_rows)*100:.1f}%)")
    print(f"[*] 100% doanh nghiệp có Email nằm ở các dòng 1 đến {len(with_email)}.")
    print(f"📁 Tệp kết quả: {CSV_FILE}")
    print("=" * 70)

if __name__ == '__main__':
    main()
