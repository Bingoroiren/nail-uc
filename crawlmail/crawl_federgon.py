import os
import re
import json
import csv
import urllib.request
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

def format_phone(p):
    if not p:
        return ""
    p_str = str(p).strip()
    return f"'{p_str}" if not p_str.startswith("'") else p_str

def extract_federgon_data():
    url = 'https://talentbusinesspartners.com/f/federgon/nl/directory'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Referer': 'https://federgon.be/',
    }
    
    # Check if scratch_tbp.html already exists, else fetch
    if os.path.exists('scratch_tbp.html') and os.path.getsize('scratch_tbp.html') > 500000:
        with open('scratch_tbp.html', encoding='utf-8') as f:
            text = f.read()
    else:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as resp:
            text = resp.read().decode('utf-8', errors='ignore')
            with open('scratch_tbp.html', 'w', encoding='utf-8') as f:
                f.write(text)

    # Reconstruct RSC stream
    raw_chunks = re.findall(r'self\.__next_f\.push\(\[\d+,\s*"(.*?)"\]\)', text, re.DOTALL)
    full_stream = ""
    for c in raw_chunks:
        try:
            full_stream += json.loads(f'"{c}"')
        except Exception:
            full_stream += c.replace('\\"', '"').replace('\\\\', '\\').replace('\\n', '\n').replace('\\/', '/')

    # Find the array of members
    idx = full_stream.find('"name":"ACE Belgium"')
    start_arr = full_stream.rfind(':[{"', 0, idx)
    if start_arr == -1:
        raise ValueError("Could not find start of member array in stream")
    start_arr += 1

    depth = 0
    end_arr = -1
    in_string = False
    escape = False
    for i in range(start_arr, len(full_stream)):
        ch = full_stream[i]
        if escape:
            escape = False
            continue
        if ch == '\\':
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string:
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    end_arr = i + 1
                    break

    arr_json = full_stream[start_arr:end_arr]
    members = json.loads(arr_json)
    print(f"Total members loaded from Federgon payload: {len(members)}")

    # Filter: Projectsourcing OR Recruitment, Search & Selection
    filtered_rows = []
    for m in members:
        name = (m.get('name') or '').strip()
        if not name or is_blacklisted_company(name):
            continue

        fv = m.get('fieldValues', {})
        sectors = fv.get('sector', [])
        
        is_ps = 'project-sourcing' in sectors
        is_rss = 'recruitment-search-selection' in sectors
        
        # Keep only if matches user criteria
        if not (is_ps or is_rss):
            continue

        city = (m.get('city') or '').strip()
        phone = format_phone(m.get('phone'))
        website = (m.get('website') or '').strip()
        description = (m.get('description') or '').strip().replace('\r', ' ').replace('\n', ' ')
        logo = (m.get('logo') or '').strip()
        
        sector_labels = []
        if is_ps:
            sector_labels.append("Projectsourcing")
        if is_rss:
            sector_labels.append("Recruitment, Search & Selection")
        # include any other sectors
        for s in sectors:
            if s not in ['project-sourcing', 'recruitment-search-selection']:
                sector_labels.append(s)

        filtered_rows.append({
            'Company_Name': name,
            'City': city,
            'Country': 'Belgium',
            'Phone': phone,
            'Website': website,
            'Federgon_Sectors': ", ".join(sector_labels),
            'Is_Projectsourcing': "Yes" if is_ps else "No",
            'Is_Recruitment_Search_Selection': "Yes" if is_rss else "No",
            'Description': description,
            'Logo_URL': logo,
            'Source': 'Federgon Directory (talentbusinesspartners.com)'
        })

    print(f"Total matching companies extracted: {len(filtered_rows)}")

    # Save to standard CSV filename: BE_AGCY_WEBD_0RAW.csv
    output_csv = 'BE_AGCY_WEBD_0RAW.csv'
    fieldnames = [
        'Company_Name', 'City', 'Country', 'Phone', 'Website',
        'Federgon_Sectors', 'Is_Projectsourcing', 'Is_Recruitment_Search_Selection',
        'Description', 'Logo_URL', 'Source'
    ]

    with open(output_csv, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(filtered_rows)

    print(f"Successfully saved {len(filtered_rows)} records to {output_csv}")

if __name__ == '__main__':
    extract_federgon_data()
