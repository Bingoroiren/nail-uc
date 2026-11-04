import os
import sys
import glob
import re
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Load Mail Tracker
tracker_emails = set()
if os.path.exists('Mail Tracker - mail.csv'):
    try:
        t_df = pd.read_csv('Mail Tracker - mail.csv', encoding='utf-8-sig', dtype=str)
        col = 'Người gửi' if 'Người gửi' in t_df.columns else t_df.columns[0]
        for val in t_df[col].dropna():
            val = str(val).strip().lower()
            if '@' in val:
                tracker_emails.add(val)
    except Exception as e:
        pass

def is_valid_usable_email(em):
    if not em or pd.isna(em):
        return False
    em = str(em).strip().lower()
    if not em or em in ['nan', 'none', 'null', '']:
        return False
    # Standard format
    if not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', em):
        return False
    # Junk & placeholder filters (Rule #3)
    junk_parts = [
        'sentry', 'wixpress', 'wordpress', 'example', 'domain.com', 'youremail',
        'your-email', 'someone', 'john.doe', 'user@domain', 'name@domain',
        'no-reply', 'noreply', 'donotreply', 'privacy@', 'gdpr@',
        'yourcompany', 'email@email.com', 'test@', 'sample@', 'mail@mail.com',
        'domain@domain.com', 'yourname@', 'email.com'
    ]
    if any(j in em for j in junk_parts):
        return False
    # File extensions
    if any(em.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.js', '.css']):
        return False
    return True

def analyze_file(filepath):
    df = None
    for enc in ['utf-8-sig', 'utf-8', 'cp1252', 'latin1']:
        try:
            df = pd.read_csv(filepath, encoding=enc, dtype=str)
            break
        except Exception:
            continue
    if df is None or df.empty:
        return None
    
    # Locate Email column
    email_col = None
    for c in df.columns:
        if c.strip().lower() in ['email', 'e-mail', 'mail']:
            email_col = c
            break
    if not email_col:
        for c in df.columns:
            if 'email' in c.strip().lower() or 'mail' in c.strip().lower():
                email_col = c
                break
    if not email_col:
        return None
        
    total_rows = len(df)
    raw_emails = df[email_col].dropna().astype(str).str.strip()
    raw_emails = raw_emails[~raw_emails.isin(['', 'nan', 'none', 'null'])]
    
    valid_emails = [e.lower() for e in raw_emails if is_valid_usable_email(e)]
    unique_valid = set(valid_emails)
    fresh_emails = set(e for e in unique_valid if e not in tracker_emails)
    
    return {
        'path': filepath,
        'filename': os.path.basename(filepath),
        'email_col': email_col,
        'total_rows': total_rows,
        'raw_email_count': len(raw_emails),
        'valid_usable_count': len(valid_emails),
        'unique_valid_count': len(unique_valid),
        'fresh_count': len(fresh_emails),
        'pct_valid': (len(valid_emails) / total_rows * 100) if total_rows else 0
    }

patterns = [
    '*.csv',
    'csdl_mlt/*.csv',
    'csdl_sk/*.csv',
    'csdl_sk_agcy/*.csv',
    'data/formatted/*.csv',
    'data/*.csv'
]

seen_files = set()
all_results = []
for pat in patterns:
    for f in glob.glob(pat):
        norm = os.path.normpath(f)
        if norm in seen_files:
            continue
        seen_files.add(norm)
        res = analyze_file(f)
        if res and res['valid_usable_count'] > 0:
            all_results.append(res)

print(f"Loaded {len(tracker_emails)} tracker emails.")
print(f"Total matching files analyzed: {len(all_results)}\n")
print(f"{'Filename':<42} | {'Rows':<7} | {'Valid':<7} | {'Unique':<7} | {'Fresh':<7} | {'Rate':<6} | {'Path'}")
print("-" * 125)
for r in sorted(all_results, key=lambda x: (x['unique_valid_count']), reverse=True):
    print(f"{r['filename'][:42]:<42} | {r['total_rows']:<7} | {r['valid_usable_count']:<7} | {r['unique_valid_count']:<7} | {r['fresh_count']:<7} | {r['pct_valid']:>5.1f}% | {r['path']}")
