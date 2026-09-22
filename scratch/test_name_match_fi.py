# -*- coding: utf-8 -*-
import sys
import re

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

LEGAL_FORMS_FI = [
    'oy', 'ab', 'oyj', 'ky', 'ay', 'tmi', 'osk', 'ry', 'ltd'
]

def clean_company_name_fi(name):
    if not name:
        return ""
    n = re.sub(r'["\'„“”«»]', '', name).strip().lower()
    tokens = n.split()
    tokens = [t for t in tokens if t not in LEGAL_FORMS_FI]
    return ' '.join(tokens).strip()

def is_valid_name_match_fi(query_name, candidate_name):
    q = clean_company_name_fi(query_name)
    c = re.sub(r'["\'„“”«»]', '', candidate_name).strip().lower()
    c_clean = clean_company_name_fi(candidate_name)
    
    if not q or not c_clean:
        return False, "EMPTY"

    if q == c_clean:
        return True, "EXACT"
        
    c_without_brackets = re.sub(r'\(.*?\)|\[.*?\]', '', c).strip()
    c_without_brackets_clean = clean_company_name_fi(c_without_brackets)
    if q == c_without_brackets_clean:
        return True, "BRACKET_MATCH"
        
    parts = re.split(r'[-–—,.:|/]', c)
    parts_clean = [clean_company_name_fi(p) for p in parts if p.strip()]
    if any(p == q for p in parts_clean):
        return True, "SEPARATOR_MATCH"
        
    return False, "NO_MATCH"

if __name__ == '__main__':
    test_cases = [
        ('Barona Oy', 'Barona Oy'),
        ('Barona Oy', 'Barona'),
        ('Barona Oy', 'Barona (Helsinki)'),
        ('Barona Oy', 'Barona - Tampere toimisto'),
        ('Barona Oy', 'Barona Construction'),
        ('Staffmax Oy', 'Staffmax Oy Ab'),
        ('Staffmax Oy', 'Staffmax - Henkilöstöpalvelut'),
        ('Staffmax Oy', 'Staffmax Logistiikka'),
        ('Eezy Henkilöstöpalvelut Oy', 'Eezy Henkilöstöpalvelut'),
        ('Eezy Henkilöstöpalvelut Oy', 'Eezy Henkilöstöpalvelut, Oulu'),
    ]

    for q, cand in test_cases:
        valid, reason = is_valid_name_match_fi(q, cand)
        print(f"Query: {q:30} | Cand: {cand:35} -> {valid} ({reason})")
