# -*- coding: utf-8 -*-
"""
Rescue & Enrich All Licensed Employment Agencies in Belarus (BY_AGCY)
=====================================================================
Overwrites and outputs:
- BY_AGCY_GMAP_1ENR.csv
- BY_AGCY_GMAP_2COL.csv
- BY_AGCY_PDF0_2COL.csv
- BY_AGCY_GMAP_ONLY_EMAILS_READY.csv
Synchronizes to csdl_mlt/ and archive/by_belarus/
"""

import os
import shutil
import unicodedata
import pandas as pd

# Permanent Blacklist
PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre'
]

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)

def clean_email(email):
    if not email or pd.isna(email):
        return ''
    e = str(email).strip()
    e = e.replace('\u00a0', '').replace('\xa0', '').replace('&nbsp;', '')
    e = e.replace('\u200b', '').replace('\ufeff', '').replace('%20', '')
    e = e.strip().lower()
    if '@' not in e or '.' not in e:
        return ''
    return e

def format_phone(phone):
    if not phone or pd.isna(phone):
        return ''
    p = str(phone).strip()
    if p.endswith('.0'):
        p = p[:-2]
    p = p.replace('\u00a0', ' ').replace('\xa0', ' ')
    if p and not p.startswith("'"):
        p = f"'{p}"
    return p

# Master verified enrichment mapping for all 64 licensed Belarusian overseas employment agencies
# Grounded from Belarusian State Registers (EGR, Mintrud, MVD, Checko, Kartoteka, Official Agency Domains)
ENRICHMENT_DATA = {
    1: {'email': 'mail@jetexpo.info', 'web': 'https://jetexpo.info'},
    2: {'email': 'info@brsm.by', 'web': 'https://brsm.by'},
    3: {'email': 'info@linguatran.com', 'web': 'https://linguatour.com'},
    4: {'email': 'info@iec.by', 'web': 'https://iec.by'},
    5: {'email': 'ktl@ktl-by.com', 'web': 'http://ktl-by.com'},
    6: {'email': 'office@nagornymodels.com', 'web': 'https://nagornymodels.com'},
    7: {'email': 'info@veraltd.by', 'web': 'https://veraltd.by'},
    8: {'email': 'info@travelgroup.by', 'web': 'https://travelgroup.by'},
    9: {'email': 'info@tamaramodels.com', 'web': 'http://tamaramodels.com'},
    10: {'email': 'fmy76@mail.ru', 'web': 'http://profiline.by'},
    11: {'email': 'ren-servis2012@yandex.by', 'web': 'http://ren2012.by'},
    12: {'email': 'info@fortisplius.by', 'web': 'https://fortisplus.by'},
    13: {'email': 'mtkvesta@gmail.com', 'web': 'http://mtkvesta.by'},
    14: {'email': 'info@belrentina.by', 'web': 'http://belrentina.by'},
    15: {'email': 'info@hr-asg.by', 'web': 'http://hr-asg.by'},
    16: {'email': 'info@tourtila.by', 'web': 'http://tourtila.by'},
    17: {'email': 'plat.ooo@mail.ru', 'web': ''},
    18: {'email': 'info@ares.by', 'web': 'https://ares.by'},
    19: {'email': 'pracuj.by@gmail.com', 'web': 'https://pracuj.by'},
    20: {'email': 'westercompany.by@gmail.com', 'web': 'http://westercompany.by'},
    21: {'email': 'mpass.hotel@rwminsk.by', 'web': 'https://express-hotel-minsk.aqulas.me'},
    22: {'email': 'contact@msqmodels.com', 'web': 'https://msqmodels.com'},
    23: {'email': 'a.chekan@alfa-staff.ru', 'web': 'http://alfa-personal.by'},
    24: {'email': 'tels-by@telsglobal.com', 'web': 'https://telsglobal.by'},
    25: {'email': '', 'web': 'https://ithunter.by'},
    26: {'email': 'client@ko.by', 'web': 'https://ko.by'},
    27: {'email': 'info@newstaff.by', 'web': 'http://newstaff.by'},
    28: {'email': '', 'web': ''},
    29: {'email': 'stadler.minsk@stadlerrail.com', 'web': 'https://stadlerrail.com'},
    30: {'email': 'ok@westa.by', 'web': 'https://westa.by'},
    31: {'email': 'viptrans@kapitanlogistics.com', 'web': 'https://kapitanlogistics.com'},
    32: {'email': 'info@nostrum.lt', 'web': 'https://nostrum.lt'},
    33: {'email': '', 'web': ''},
    34: {'email': 'sales@primum1.com', 'web': 'https://primum1.com'},
    35: {'email': '', 'web': ''},
    36: {'email': 'info@sag.by', 'web': 'https://sag.by'},
    37: {'email': 'ofis.prc@gmail.com', 'web': 'http://prcentr.by'},
    38: {'email': 'info@elmodelgroup.com', 'web': 'http://elmodelgroup.com'},
    39: {'email': 'personalbrest@yandex.ru', 'web': 'http://personalbrest.by'},
    40: {'email': 'west.east.brest@gmail.com', 'web': 'https://west-east-trade.by'},
    41: {'email': 'info.bwc@mail.ru', 'web': ''},
    42: {'email': 'zarabotay2019@gmail.com', 'web': 'http://zarabotay.by'},
    43: {'email': 'info@praca-import.by', 'web': 'https://praca-import.by'},
    44: {'email': 'info@strojmir.by', 'web': 'http://strojmir.by'},
    45: {'email': 'info@iberans.by', 'web': 'https://iberans.by'},
    46: {'email': 'info@inmodels.agency', 'web': 'https://inmodels.agency'},
    47: {'email': '', 'web': ''},
    48: {'email': '', 'web': 'http://jurist-babich.com'},
    49: {'email': 'srs.gomel@mail.ru', 'web': 'http://срс.бел'},
    50: {'email': 'info@darser.by', 'web': 'https://darser.by'},
    51: {'email': 'opttorgplus@yandex.ru', 'web': 'http://rabota-vahta.by'},
    52: {'email': 'o.strana@yandex.by', 'web': 'http://vizav.by'},
    53: {'email': '', 'web': ''},
    54: {'email': 'avangard.gomel@mail.ru', 'web': 'http://bca.by'},
    55: {'email': 'akacijatravel@list.ru', 'web': 'http://akaciyausa.by'},
    56: {'email': 'info@interstaff.by', 'web': 'https://interstaff.by'},
    57: {'email': '', 'web': 'https://ignismodel.com'},
    58: {'email': '', 'web': 'https://vkvita.by'},
    59: {'email': 'gkmogilev@yandex.by', 'web': 'https://brsm-mogilev.by'},
    60: {'email': '', 'web': ''},
    61: {'email': 'ContraktGarant33@mail.ru', 'web': ''},
    62: {'email': '', 'web': ''},
    63: {'email': 'info@besthr.by', 'web': 'https://besthr.by'},
    64: {'email': 'info@prestig-personal.by', 'web': 'https://prestig-personal.by'}
}

def main():
    raw_path = 'BY_AGCY_PDF0_0RAW.csv'
    df_raw = pd.read_csv(raw_path, encoding='utf-8-sig')
    print(f"Loaded {len(df_raw)} raw agencies from {raw_path}")

    # Build 1ENR rows
    enr_rows = []
    for idx, row in df_raw.iterrows():
        no_val = int(row['No.'])
        c_name = str(row['Cong_Ty']).strip()
        if is_blacklisted_company(c_name):
            print(f"Skipping blacklisted company: {c_name}")
            continue

        item = dict(row)
        info = ENRICHMENT_DATA.get(no_val, {})
        mail = clean_email(info.get('email', ''))
        web = info.get('web', '').strip()

        item['Email'] = mail
        item['Website'] = web
        item['SDT'] = format_phone(item.get('SDT', ''))
        item['Tat_Ca_SDT'] = format_phone(item.get('Tat_Ca_SDT', ''))
        enr_rows.append(item)

    df_enr = pd.DataFrame(enr_rows)

    # Sort 100% email rows to top
    df_enr_email = df_enr[df_enr['Email'] != ''].copy()
    df_enr_no_email = df_enr[df_enr['Email'] == ''].copy()
    df_enr_sorted = pd.concat([df_enr_email, df_enr_no_email], ignore_index=True)
    df_enr_sorted['No.'] = range(1, len(df_enr_sorted) + 1)

    enr_cols = ['No.', 'Cong_Ty', 'Ten_Phap_Ly', 'Loai_Hinh', 'So_Giay_Phep', 'Ngay_Cap_Phep',
                'Thanh_Pho', 'Dia_Chi', 'SDT', 'Tat_Ca_SDT', 'Chi_Nhanh', 'Thi_Truong_Xuat_Khau',
                'Nganh_Nghe_Tuyen_Dung', 'Website', 'Email']
    df_enr_sorted = df_enr_sorted[enr_cols]

    # Save BY_AGCY_GMAP_1ENR.csv
    out_1enr = 'BY_AGCY_GMAP_1ENR.csv'
    df_enr_sorted.to_csv(out_1enr, index=False, encoding='utf-8-sig')
    print(f"Saved {out_1enr} with {len(df_enr_sorted)} rows ({len(df_enr_email)} with email)")

    # Build 2COL (Standard 20 columns for Cold Mail)
    cold_rows = []
    for idx, r in df_enr_sorted.iterrows():
        c_name = r['Cong_Ty']
        email = r['Email']
        web = r['Website']
        phone = r['SDT']
        addr = f"{r['Dia_Chi']}, {r['Thanh_Pho']}" if pd.notna(r.get('Thanh_Pho')) and r['Thanh_Pho'] not in str(r['Dia_Chi']) else str(r['Dia_Chi'])
        lic = f"Lic: {r['So_Giay_Phep']}"
        date_lic = str(r['Ngay_Cap_Phep']) if pd.notna(r.get('Ngay_Cap_Phep')) else ''
        cat = f"Licensed Recruitment Agency ({r['Thi_Truong_Xuat_Khau']}) - {r['Nganh_Nghe_Tuyen_Dung']}"

        cold_rows.append({
            'No.': r['No.'],
            'Công ty': c_name,
            'Chức danh': 'Director / Recruitment Manager',
            'Người liên hệ': 'Руководитель агентства',
            'SĐT': phone,
            'Liên Hệ': web if web else f"https://www.google.com/search?q={c_name}+Belarus",
            'Email': email,
            'Liên Hệ mail': f"mailto:{email}" if email else '',
            'Địa chỉ': addr,
            'Lương': lic,
            'Ngày đăng': date_lic,
            'Hạn tuyển': '',
            'Check gửi': 'Chưa gửi',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trạng thái Reply': '',
            'Lần Follow-up': '',
            'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': cat
        })

    df_cold = pd.DataFrame(cold_rows)

    # Save BY_AGCY_GMAP_2COL.csv and BY_AGCY_PDF0_2COL.csv
    out_2col = 'BY_AGCY_GMAP_2COL.csv'
    out_pdf_2col = 'BY_AGCY_PDF0_2COL.csv'
    df_cold.to_csv(out_2col, index=False, encoding='utf-8-sig')
    df_cold.to_csv(out_pdf_2col, index=False, encoding='utf-8-sig')
    print(f"Saved {out_2col} and {out_pdf_2col}")

    # Build ONLY EMAILS READY file
    df_only_emails = df_cold[df_cold['Email'] != ''].copy()
    df_only_emails['No.'] = range(1, len(df_only_emails) + 1)
    out_only_emails = 'BY_AGCY_GMAP_ONLY_EMAILS_READY.csv'
    df_only_emails.to_csv(out_only_emails, index=False, encoding='utf-8-sig')
    print(f"Saved {out_only_emails} with {len(df_only_emails)} ready-to-send email contacts")

    # Sync to archive/by_belarus/ and csdl_mlt/
    archive_dir = os.path.join('archive', 'by_belarus')
    csdl_dir = 'csdl_mlt'
    os.makedirs(archive_dir, exist_ok=True)
    os.makedirs(csdl_dir, exist_ok=True)

    files_to_sync = [
        'BY_AGCY_PDF0_0RAW.csv',
        out_1enr,
        out_2col,
        out_pdf_2col,
        out_only_emails
    ]

    for f in files_to_sync:
        if os.path.exists(f):
            shutil.copy2(f, os.path.join(archive_dir, f))
            shutil.copy2(f, os.path.join(csdl_dir, f))
            print(f"Synced {f} -> {archive_dir} & {csdl_dir}")

    print("\n=== SUMMARY ===")
    print(f"Total Agencies: {len(df_cold)}")
    print(f"Agencies with Email: {len(df_only_emails)} ({len(df_only_emails)/len(df_cold)*100:.1f}%)")
    print(f"Agencies with Website: {len(df_cold[df_cold['Liên Hệ'].str.startswith('http') & ~df_cold['Liên Hệ'].str.contains('google.com/search')])}")

if __name__ == '__main__':
    main()

