import csv
import os
import shutil

INPUT_CSV = r"d:\glc\nail uc\construction_australia.csv"
BACKUP_CSV = r"d:\glc\nail uc\construction_australia_backup.csv"

ALLOWED_CATEGORIES = {
    "contractor",
    "construction company",
    "home builder",
    "office refurbishment service",
    "excavating contractor",
    "custom home builder"
}

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
        print(f"Error: Original file {INPUT_CSV} not found.")
        return

    # 1. Back up original file
    print(f"[*] Backing up original CSV to {BACKUP_CSV}...")
    shutil.copy2(INPUT_CSV, BACKUP_CSV)

    # 2. Read rows and track fieldnames
    with open(INPUT_CSV, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames) if reader.fieldnames else []
        rows = list(reader)

    if 'Permanently_Closed' not in fieldnames:
        fieldnames.append('Permanently_Closed')

    for row in rows:
        if None in row:
            row['Permanently_Closed'] = row[None][0] if row[None] else 'No'
            del row[None]
        if 'Permanently_Closed' not in row or not row['Permanently_Closed']:
            row['Permanently_Closed'] = 'No'

    print(f"[*] Loaded {len(rows)} raw rows.")

    # 3. Remove identical duplicate rows
    seen = set()
    unique_rows = []
    duplicate_count = 0
    for row in rows:
        row_tuple = tuple(row.get(col, '') for col in fieldnames)
        if row_tuple not in seen:
            seen.add(row_tuple)
            unique_rows.append(row)
        else:
            duplicate_count += 1

    print(f"[*] Removed {duplicate_count} identical duplicate rows. Unique rows remaining: {len(unique_rows)}.")

    # 4. Strict category filter
    filtered_rows = []
    filtered_out_count = 0
    for row in unique_rows:
        category = row.get("Category", "").strip().lower()
        if category and not any(tag in category for tag in ALLOWED_CATEGORIES):
            filtered_out_count += 1
            continue
        filtered_rows.append(row)
    unique_rows = filtered_rows
    print(f"[*] Filtered out {filtered_out_count} rows with irrelevant categories. Rows remaining: {len(unique_rows)}.")

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
        print("[SUCCESS] CSV Preprocessing complete!")
    except Exception as write_err:
        print(f"[ERROR] Failed to write preprocessed data: {write_err}")
        if os.path.exists(temp_csv):
            os.remove(temp_csv)
        raise write_err

if __name__ == "__main__":
    preprocess()
