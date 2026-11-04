import os
import re
import csv
import json
import time
import urllib.request
import urllib.parse
from bs4 import BeautifulSoup
import unicodedata

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

# Excluded activities: Model agencies, mannequins, hostesses
EXCLUDED_ACTIVITIES_KEYWORDS = [
    'fotomodellen', 'mannequins', 'hostessen', 'mannequin', 'hôtesses',
    'dergelijke', 'modellenbureau', 'mannequinat', 'acteurs voor film'
]

def is_excluded_activity(activity_text, nace_code):
    if not activity_text and not nace_code:
        return False
    act = str(activity_text).lower()
    code = str(nace_code)
    # 78.10005 is model agency
    if '78.10005' in code or '7810005' in code:
        return True
    return any(kw in act for kw in EXCLUDED_ACTIVITIES_KEYWORDS)

def clean_text(s):
    if not s:
        return ""
    return str(s).replace('\u00a0', ' ').replace('\xa0', ' ').replace('&nbsp;', ' ').strip()

def parse_kbo_page(html, current_postcode, nace_code):
    soup = BeautifulSoup(html, 'html.parser')
    results = []
    
    tables = soup.find_all('table')
    target_table = None
    for tbl in tables:
        txt = tbl.get_text()
        if 'Ondernemings' in txt and 'Naam' in txt and 'Adres' in txt:
            target_table = tbl
            break
            
    if not target_table:
        return results, False, 0

    rows = target_table.find_all('tr')
    for tr in rows:
        tds = tr.find_all('td')
        if len(tds) < 6:
            continue
            
        texts = [clean_text(td.get_text()) for td in tds]
        
        # When _vest=on (without vest=true):
        # texts[0]: Index (e.g. '1')
        # texts[1]: ENT/VE + Status (e.g. 'ENT RPActief' or 'ENT RP Actief')
        # texts[2]: Ondernemingsnummer (e.g. '0790.515.554')
        # texts[3]: Naam (e.g. 'A2LD GESTION')
        # texts[4]: Adres (e.g. 'Joseph Stevensstraat 7 1000 Brussel')
        # texts[5]: Activiteiten (e.g. 'Arbeidsbemiddeling')
        # texts[6]: Nacebelcode (e.g. '78.100')
        
        # If vest=true is present, Vestigingseenheidsnummer is at texts[3], and columns shift by 1
        if len(texts) >= 8 and (texts[3].startswith('2.') or len(texts[3]) == 13):
            kbo_num = texts[2]
            ve_num = texts[3]
            name = texts[4]
            address = texts[5]
            activity = texts[6]
            nace_val = texts[7] if len(texts) > 7 else nace_code
        elif len(texts) >= 7:
            kbo_num = texts[2]
            ve_num = ""
            name = texts[3]
            address = texts[4]
            activity = texts[5]
            nace_val = texts[6]
        else:
            continue
            
        ent_raw = texts[1]
        status = "Actief" if "actief" in ent_raw.lower() else ("Stopgezet" if "stop" in ent_raw.lower() else "")
        ent_type = re.sub(r'(?i)actief|stopgezet', '', ent_raw).strip()
            
        if not name or name == 'Naam' or is_blacklisted_company(name):
            continue
            
        # Filter out model agencies, mannequins, hostesses
        if is_excluded_activity(activity, nace_val):
            continue

        results.append({
            'Company_Name': name,
            'KBO_Number': kbo_num,
            'VE_Number': ve_num,
            'Type': ent_type,
            'Status': status,
            'Address': address,
            'Postcode': current_postcode,
            'Country': 'Belgium',
            'Activity': activity,
            'NACE_Code': nace_val,
            'Phone': '',
            'Website': '',
            'Source': f'KBO Public Search (NACE {nace_code})'
        })
        
    has_next = False
    for a in soup.find_all('a'):
        t = a.get_text(strip=True).lower()
        if 'volgende' in t:
            has_next = True
            break
            
    total_found = len(results)
    m = re.search(r'(\d+)\s+entiteiten', html)
    if m:
        try:
            total_found = int(m.group(1))
        except Exception:
            pass

    return results, has_next, total_found

def scrape_kbo(limit_postcodes=None):
    output_csv = 'BE_AGCY_KBO0_0RAW.csv'
    cache_file = 'kbo_progress_cache.json'
    
    postcodes_file = 'belgium_postcodes.json'
    if not os.path.exists(postcodes_file):
        print(f"Error: {postcodes_file} not found.")
        return
        
    with open(postcodes_file, encoding='utf-8') as f:
        postcodes = json.load(f)
        
    valid_postcodes = [p for p in postcodes if len(p) == 4 and p >= '1000' and p <= '9999']
    if limit_postcodes:
        valid_postcodes = valid_postcodes[:limit_postcodes]
        
    print(f"Loaded {len(valid_postcodes)} Belgian postcodes to scan.")
    
    completed_pairs = set()
    if os.path.exists(cache_file):
        try:
            with open(cache_file, encoding='utf-8') as f:
                completed_pairs = set(json.load(f))
        except Exception:
            pass
            
    seen_kbo_numbers = set()
    if os.path.exists(output_csv):
        with open(output_csv, encoding='utf-8-sig', mode='r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                num = row.get('KBO_Number') or row.get('Company_Name')
                if num:
                    seen_kbo_numbers.add(num)
        print(f"Resuming: found {len(seen_kbo_numbers)} already scraped records in {output_csv}")
    else:
        with open(output_csv, 'w', encoding='utf-8-sig', newline='') as f:
            fieldnames = [
                'Company_Name', 'KBO_Number', 'VE_Number', 'Type', 'Status',
                'Address', 'Postcode', 'Country', 'Activity', 'NACE_Code',
                'Phone', 'Website', 'Source'
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'nl-NL,nl;q=0.9,en-US;q=0.8',
        'Referer': 'https://kbopub.economie.fgov.be/kbopub/zoekactiviteitform.html'
    }

    nace_codes = ['78100', '78200', '78.300']
    total_added = 0

    for idx, pc in enumerate(valid_postcodes):
        for nace in nace_codes:
            pair_key = f"{pc}_{nace}"
            if pair_key in completed_pairs:
                continue
                
            page = 1
            while True:
                params = {
                    'nacecodes': nace,
                    'keuzeopzloc': 'postnr',
                    'postnummer1': pc,
                    'gemeente1': '', 'gemeente2': '', 'gemeente3': '', 'gemeente0': '',
                    'postnummer2': '', 'postnummer3': '', 'postnummer4': '',
                    '_ondNP': 'on',
                    'ondRP': 'true',
                    '_ondRP': 'on',
                    '_vest': 'on',
                    'filterEnkelActieve': 'true',
                    '_filterEnkelActieve': 'on',
                    'actionLu': 'Zoeken'
                }
                if page > 1:
                    params['page'] = str(page)
                    
                url = 'https://kbopub.economie.fgov.be/kbopub/zoekactiviteitform.html?' + urllib.parse.urlencode(params)
                
                try:
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        html = resp.read().decode('utf-8', errors='ignore')
                except urllib.error.HTTPError as e:
                    if e.code == 404:
                        break
                    print(f"HTTP Error {e.code} for PC {pc} NACE {nace} page {page}. Retrying...")
                    time.sleep(2)
                    continue
                except Exception as e:
                    print(f"Network error for PC {pc} page {page}: {e}. Retrying...")
                    time.sleep(2)
                    continue
                    
                records, has_next, total_found = parse_kbo_page(html, pc, nace)
                
                new_records = []
                for r in records:
                    unique_id = r['KBO_Number'] if r['KBO_Number'] else (r['Company_Name'] + "_" + pc)
                    if unique_id not in seen_kbo_numbers:
                        seen_kbo_numbers.add(unique_id)
                        new_records.append(r)
                        
                if new_records:
                    with open(output_csv, 'a', encoding='utf-8-sig', newline='') as f:
                        fieldnames = [
                            'Company_Name', 'KBO_Number', 'VE_Number', 'Type', 'Status',
                            'Address', 'Postcode', 'Country', 'Activity', 'NACE_Code',
                            'Phone', 'Website', 'Source'
                        ]
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writerows(new_records)
                        f.flush()
                    total_added += len(new_records)
                    print(f"[{idx+1}/{len(valid_postcodes)}] PC {pc} | NACE {nace} | Page {page} -> +{len(new_records)} companies (Total: {total_added})")
                    
                if not has_next or page >= 10:
                    break
                page += 1
                time.sleep(0.3)
                
            completed_pairs.add(pair_key)
            if len(completed_pairs) % 20 == 0:
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(list(completed_pairs), f)
                    
        if (idx + 1) % 50 == 0:
            print(f"Progress: {idx+1}/{len(valid_postcodes)} postcodes processed. Total records: {len(seen_kbo_numbers)}")

    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(list(completed_pairs), f)

    print(f"\nCOMPLETED! Total unique active enterprises saved: {len(seen_kbo_numbers)}")

if __name__ == '__main__':
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    scrape_kbo(limit_postcodes=limit)
