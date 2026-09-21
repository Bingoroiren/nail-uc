# -*- coding: utf-8 -*-
import sys
import re

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

LEGAL_PREFIXES = [
    'uab', 'ab', 'mb', 'všį', 'vsi', 'iį', 'ii', 'žūb', 'zub', 'tūb', 'tub'
]

def clean_company_name(name):
    if not name:
        return ""
    # Remove quotes
    n = re.sub(r'["\'„“”«»]', '', name).strip().lower()
    # Remove legal forms
    tokens = n.split()
    tokens = [t for t in tokens if t not in LEGAL_PREFIXES]
    return ' '.join(tokens).strip()

def is_valid_name_match(query_name, candidate_name):
    q = clean_company_name(query_name)
    c = re.sub(r'["\'„“”«»]', '', candidate_name).strip().lower()
    c_clean = clean_company_name(candidate_name)
    
    if not q or not c_clean:
        return False, "EMPTY"

    # Exact match after removing legal prefixes
    if q == c_clean:
        return True, "EXACT"
        
    # Check if candidate consists of query + bracketed info
    # e.g., 'Samsonas (Vilniaus filialas)' -> remove brackets
    c_without_brackets = re.sub(r'\(.*?\)|\[.*?\]', '', c).strip()
    c_without_brackets_clean = clean_company_name(c_without_brackets)
    if q == c_without_brackets_clean:
        return True, "BRACKET_MATCH"
        
    # Check if candidate is separated by punctuation (-, –, —, ,, ., :, |)
    # e.g. 'Samsonas - Kaunas', 'Samsonas, UAB', 'Samsonas | Fabrikas'
    parts = re.split(r'[-–—,.:|/]', c)
    parts_clean = [clean_company_name(p) for p in parts if p.strip()]
    if any(p == q for p in parts_clean):
        return True, "SEPARATOR_MATCH"
        
    return False, "NO_MATCH"

if __name__ == '__main__':
    test_cases = [
        ('UAB Samsonas', 'Samsonas, UAB'),
        ('UAB Samsonas', 'Samsonas (Vilnius)'),
        ('UAB Samsonas', 'Samsonas - Kaunas gamykla'),
        ('UAB Samsonas', 'Samsonas Construction'),
        ('Bio Sala', 'Bio Sala (Parduotuvė)'),
        ('Bio Sala', 'Bio Sala - PC Akropolis'),
        ('Bio Sala', 'Bio Sala Grožio Namai'),
        ('Vilniaus paukštynas', 'AB Vilniaus paukštynas'),
        ('Vilniaus paukštynas', 'Vilniaus paukštynas, paukštidė Nr. 3'),
        ('Vilniaus paukštynas', 'Vilniaus paukštyno kiaušiniai'),
        ('Biovela', 'Biovela - Utenos mėsa, UAB'),
    ]

    for q, cand in test_cases:
        valid, reason = is_valid_name_match(q, cand)
        print(f"Query: {q:20} | Cand: {cand:35} -> {valid} ({reason})")
