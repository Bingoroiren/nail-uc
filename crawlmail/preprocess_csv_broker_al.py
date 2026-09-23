import csv
import os
import shutil
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATE_INPUTS = [
    os.path.join(BASE_DIR, "data", "raw", "broker_albania.csv"),
    os.path.join(BASE_DIR, "broker_albania.csv")
]

INPUT_CSV = None
for candidate in CANDIDATE_INPUTS:
    if os.path.exists(candidate):
        INPUT_CSV = candidate
        break

if not INPUT_CSV:
    INPUT_CSV = CANDIDATE_INPUTS[0]

BACKUP_CSV = os.path.join(os.path.dirname(INPUT_CSV), "broker_albania_backup.csv")

# Allowed Albania Broker & Recruitment Category Tags (Strict 5-Tag Filtering)
ALLOWED_CATEGORIES = {
    "shërbim konsulent për burime njerëzore",
    "sherbim konsulent per burime njerezore",
    "agjenci punësimi",
    "agjenci punesimi",
    "qendra e punësimit",
    "qendra e punesimit",
    "rekrutues",
    "agjenci për punë të përkohshme",
    "agjenci per pune te perkohshme"
}

def normalize_text(text):
    if not text:
        return ""
    text = text.lower().strip()
    replacements = {
        'ë': 'e', 'ç': 'c', 'é': 'e', 'è': 'e'
    }
    for orig, rep in replacements.items():
        text = text.replace(orig, rep)
    return text

def normalize_website(url):
    if not url:
        return ""
    url = url.strip().lower()
    if url.startswith("http://"):
        url = url[7:]
    elif url.startswith("https://"):
        url = url[8:]
    if url.startswith("www."):
        url = url[4:]
    if url.endswith("/"):
        url = url[:-1]
    return url

def preprocess():
    if not os.path.exists(INPUT_CSV):
        print(f"[-] Input file {INPUT_CSV} not found. Nothing to preprocess.")
        return

    # 1. Back up original file
    print(f"[*] Backing up original CSV to {BACKUP_CSV}...")
    shutil.copy2(INPUT_CSV, BACKUP_CSV)

    # 2. Read rows and track fieldnames
    with open(INPUT_CSV, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames) if reader.fieldnames else []
        rows = list(reader)

    if not fieldnames:
        print("[-] CSV is empty.")
        return

    if 'Permanently_Closed' not in fieldnames:
        fieldnames.append('Permanently_Closed')

    for row in rows:
        if None in row:
            row['Permanently_Closed'] = row[None][0] if row[None] else 'No'
            del row[None]
        if 'Permanently_Closed' not in row or not row['Permanently_Closed']:
            row['Permanently_Closed'] = 'No'

    print(f"[*] Loaded {len(rows)} raw rows from {INPUT_CSV}.")

    # 3. Remove identical duplicate rows / URLs
    seen_urls = set()
    seen_rows = set()
    unique_rows = []
    duplicate_count = 0

    for row in rows:
        url = row.get("URL", "").strip().lower()
        row_tuple = tuple(row.get(col, '') for col in fieldnames)
        
        # Check place ID or full row duplicate
        if url and url in seen_urls:
            duplicate_count += 1
            continue
        if row_tuple in seen_rows:
            duplicate_count += 1
            continue
            
        if url:
            seen_urls.add(url)
        seen_rows.add(row_tuple)
        unique_rows.append(row)

    print(f"[*] Removed {duplicate_count} duplicate rows. Unique rows remaining: {len(unique_rows)}.")

    # 4. Strict category tag filter
    filtered_rows = []
    filtered_out_count = 0
    for row in unique_rows:
        category = row.get("Category", "").strip()
        cat_lower = category.lower()
        cat_norm = normalize_text(category)
        
        is_match = False
        for tag in ALLOWED_CATEGORIES:
            tag_norm = normalize_text(tag)
            if tag in cat_lower or tag_norm in cat_norm:
                is_match = True
                break
                
        if not is_match:
            filtered_out_count += 1
            continue
            
        filtered_rows.append(row)

    unique_rows = filtered_rows
    print(f"[*] Filtered out {filtered_out_count} rows with non-qualifying categories. Qualifying rows remaining: {len(unique_rows)}.")

    # 5. Format Phone numbers and clean spaces
    for row in unique_rows:
        phone = row.get("Phone", "").strip()
        if phone:
            while phone.startswith("'"):
                phone = phone[1:]
            row["Phone"] = f"'{phone}"
        else:
            row["Phone"] = ""

    # 6. Group by normalized website
    unique_rows.sort(key=lambda r: (
        0 if normalize_website(r.get("Website", "")) else 1,
        normalize_website(r.get("Website", ""))
    ))

    # 7. Write back to original CSV file
    print(f"[*] Writing preprocessed data back to {INPUT_CSV}...")
    temp_csv = INPUT_CSV + ".tmp"
    try:
        with open(temp_csv, mode="w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(unique_rows)
        if os.path.exists(INPUT_CSV):
            os.remove(INPUT_CSV)
        os.rename(temp_csv, INPUT_CSV)
        print(f"[SUCCESS] CSV Preprocessing complete! {len(unique_rows)} clean records ready.")
    except Exception as write_err:
        print(f"[ERROR] Failed to write preprocessed data: {write_err}")
        if os.path.exists(temp_csv):
            os.remove(temp_csv)
        raise write_err

if __name__ == "__main__":
    preprocess()
