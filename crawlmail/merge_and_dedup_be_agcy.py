import os
import re
import csv
import json
import unicodedata
from difflib import SequenceMatcher

# 1. Permanent Company Blacklist (Workspace Rule)
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

def clean_comp_name(name):
    if not name:
        return ""
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n = ''.join(c for c in n if not unicodedata.combining(c))
    # Strip Belgian legal forms and common generic suffixes
    legal_patterns = r'\b(nv|bvba|bv|sprl|srl|sa|scrl|cvba|vof|snc|commv|scs|gmbh|se|asbl|vzw|ebvba|holding|group|belgium|belgie|belgique)\b'
    n = re.sub(legal_patterns, ' ', n)
    n = re.sub(r'[^a-z0-9]', ' ', n)
    return ' '.join(n.split())

def are_names_similar(name1, name2):
    c1 = clean_comp_name(name1)
    c2 = clean_comp_name(name2)
    if not c1 or not c2:
        return False
    if c1 == c2:
        return True
    # Subset matching for longer names (len >= 6)
    if len(c1) >= 6 and len(c2) >= 6:
        if c1 in c2 or c2 in c1:
            return True
        # Sequence matcher ratio >= 0.88
        ratio = SequenceMatcher(None, c1, c2).ratio()
        if ratio >= 0.88:
            return True
    return False

def format_phone(p):
    if not p:
        return ""
    p_str = str(p).strip()
    return f"'{p_str}" if not p_str.startswith("'") else p_str

def merge_datasets():
    fed_file = 'BE_AGCY_WEBD_0RAW.csv'
    kbo_file = 'BE_AGCY_KBO0_0RAW.csv'
    out_file = 'BE_AGCY_COMB_0RAW.csv'

    if not os.path.exists(fed_file) or not os.path.exists(kbo_file):
        print("Error: Input files missing.")
        return

    with open(fed_file, encoding='utf-8-sig') as f:
        fed_rows = list(csv.DictReader(f))

    with open(kbo_file, encoding='utf-8-sig') as f:
        kbo_rows = list(csv.DictReader(f))

    print(f"Loaded {len(fed_rows)} Federgon companies and {len(kbo_rows)} KBO companies.")

    merged_records = []
    # Build lookup index for KBO records by cleaned name
    kbo_used = set()
    kbo_lookup = {}
    for idx, kr in enumerate(kbo_rows):
        cname = clean_comp_name(kr['Company_Name'])
        if cname:
            if cname not in kbo_lookup:
                kbo_lookup[cname] = []
            kbo_lookup[cname].append((idx, kr))

    # 1. Process Federgon records and match with KBO
    matched_count = 0
    for fr in fed_rows:
        fname = fr['Company_Name']
        if is_blacklisted_company(fname):
            continue

        fcname = clean_comp_name(fname)
        matched_kbo_idx = None
        matched_kbo_row = None

        # Check exact cleaned match
        if fcname in kbo_lookup:
            for idx, kr in kbo_lookup[fcname]:
                if idx not in kbo_used:
                    matched_kbo_idx = idx
                    matched_kbo_row = kr
                    break

        # Check fuzzy match if not found
        if matched_kbo_idx is None:
            for cname, items in kbo_lookup.items():
                if are_names_similar(fcname, cname):
                    for idx, kr in items:
                        if idx not in kbo_used:
                            matched_kbo_idx = idx
                            matched_kbo_row = kr
                            break
                if matched_kbo_idx is not None:
                    break

        if matched_kbo_row:
            kbo_used.add(matched_kbo_idx)
            matched_count += 1
            merged_records.append({
                'Company_Name': fname,
                'KBO_Number': matched_kbo_row.get('KBO_Number', ''),
                'City': fr.get('City') or matched_kbo_row.get('Postcode', ''),
                'Postcode': matched_kbo_row.get('Postcode', ''),
                'Address': matched_kbo_row.get('Address', ''),
                'Country': 'Belgium',
                'Phone': format_phone(fr.get('Phone') or matched_kbo_row.get('Phone', '')),
                'Website': fr.get('Website', ''),
                'Activity': matched_kbo_row.get('Activity', '') or fr.get('Federgon_Sectors', ''),
                'NACE_Code': matched_kbo_row.get('NACE_Code', ''),
                'Federgon_Sectors': fr.get('Federgon_Sectors', ''),
                'Description': fr.get('Description', ''),
                'Source': 'Federgon + KBO Public Search'
            })
        else:
            merged_records.append({
                'Company_Name': fname,
                'KBO_Number': '',
                'City': fr.get('City', ''),
                'Postcode': '',
                'Address': '',
                'Country': 'Belgium',
                'Phone': format_phone(fr.get('Phone', '')),
                'Website': fr.get('Website', ''),
                'Activity': fr.get('Federgon_Sectors', ''),
                'NACE_Code': '',
                'Federgon_Sectors': fr.get('Federgon_Sectors', ''),
                'Description': fr.get('Description', ''),
                'Source': 'Federgon Directory'
            })

    print(f"Matched {matched_count} Federgon companies with KBO records.")

    # 2. Append remaining KBO records
    seen_kbo_names = set()
    for idx, kr in enumerate(kbo_rows):
        if idx in kbo_used:
            continue
        kname = kr['Company_Name']
        if is_blacklisted_company(kname):
            continue
        kcname = clean_comp_name(kname)
        if kcname in seen_kbo_names:
            continue
        seen_kbo_names.add(kcname)

        merged_records.append({
            'Company_Name': kname,
            'KBO_Number': kr.get('KBO_Number', ''),
            'City': kr.get('Postcode', ''),
            'Postcode': kr.get('Postcode', ''),
            'Address': kr.get('Address', ''),
            'Country': 'Belgium',
            'Phone': format_phone(kr.get('Phone', '')),
            'Website': kr.get('Website', ''),
            'Activity': kr.get('Activity', ''),
            'NACE_Code': kr.get('NACE_Code', ''),
            'Federgon_Sectors': '',
            'Description': '',
            'Source': 'KBO Public Search'
        })

    print(f"Total merged & deduplicated companies: {len(merged_records)}")

    # Write output CSV
    fieldnames = [
        'Company_Name', 'KBO_Number', 'City', 'Postcode', 'Address', 'Country',
        'Phone', 'Website', 'Activity', 'NACE_Code', 'Federgon_Sectors',
        'Description', 'Source'
    ]
    with open(out_file, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(merged_records)

    print(f"Saved merged dataset to {out_file}")

if __name__ == '__main__':
    merge_datasets()
