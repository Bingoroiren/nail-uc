import csv
import os
import shutil

INPUT_CSV = r"d:\glc\nail uc\nail_salons_australia.csv"
BACKUP_CSV = r"d:\glc\nail uc\nail_salons_australia_backup.csv"

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
        fieldnames = reader.fieldnames
        rows = list(reader)

    print(f"[*] Loaded {len(rows)} raw rows.")

    # 3. Remove identical duplicate rows
    seen = set()
    unique_rows = []
    duplicate_count = 0
    for row in rows:
        # Create a representation of the row based on field values
        row_tuple = tuple(row.get(col, '') for col in fieldnames)
        if row_tuple not in seen:
            seen.add(row_tuple)
            unique_rows.append(row)
        else:
            duplicate_count += 1

    print(f"[*] Removed {duplicate_count} identical duplicate rows. Unique rows remaining: {len(unique_rows)}.")

    # 4. Format Phone numbers and clean spaces
    for row in unique_rows:
        phone = row.get("Phone", "").strip()
        if phone:
            # Strip all leading single quotes
            while phone.startswith("'"):
                phone = phone[1:]
            # Ensure it starts with exactly one single quote
            row["Phone"] = f"'{phone}"
        else:
            row["Phone"] = ""

    # 5. Group by normalized website
    # Sort key: 
    #   First element: 0 if website is not empty, 1 if empty (puts empty websites at the end)
    #   Second element: the normalized website string (to sort/group them together)
    unique_rows.sort(key=lambda r: (
        0 if normalize_website(r.get("Website", "")) else 1,
        normalize_website(r.get("Website", ""))
    ))

    # 6. Write back to original CSV file
    print(f"[*] Writing preprocessed data back to {INPUT_CSV}...")
    with open(INPUT_CSV, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(unique_rows)

    print("[SUCCESS] CSV Preprocessing complete!")

if __name__ == "__main__":
    preprocess()
