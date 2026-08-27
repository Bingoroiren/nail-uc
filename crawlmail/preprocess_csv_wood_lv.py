import csv
import os
import shutil

INPUT_CSV  = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "wood_latvia.csv")
BACKUP_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "wood_latvia_backup.csv")

ALLOWED_CATEGORIES = {
    "galdniecība",
    "mēbeļu izgatavotājs",
    "galdnieks",
    "kokmateriālu piegādātājs",
    "kokzāģētava"
}


def normalize_website(url):
    if not url:
        return ""
    url = url.strip().lower()
    for prefix in ("https://", "http://"):
        if url.startswith(prefix):
            url = url[len(prefix):]
    if url.startswith("www."):
        url = url[4:]
    if url.endswith("/"):
        url = url[:-1]
    return url


def preprocess():
    if not os.path.exists(INPUT_CSV):
        print(f"Error: Original file {INPUT_CSV} not found.")
        return

    print(f"[*] Backing up original CSV to {BACKUP_CSV}...")
    shutil.copy2(INPUT_CSV, BACKUP_CSV)

    with open(INPUT_CSV, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames) if reader.fieldnames else []
        rows = list(reader)

    if "Permanently_Closed" not in fieldnames:
        fieldnames.append("Permanently_Closed")

    for row in rows:
        if None in row:
            row["Permanently_Closed"] = row[None][0] if row[None] else "No"
            del row[None]
        if "Permanently_Closed" not in row or not row["Permanently_Closed"]:
            row["Permanently_Closed"] = "No"

    print(f"[*] Loaded {len(rows)} raw rows.")

    # Remove identical duplicates
    seen = set()
    unique_rows = []
    dup_count = 0
    for row in rows:
        row_tuple = tuple(row.get(col, "") for col in fieldnames)
        if row_tuple not in seen:
            seen.add(row_tuple)
            unique_rows.append(row)
        else:
            dup_count += 1
    print(f"[*] Removed {dup_count} duplicate rows. Remaining: {len(unique_rows)}.")

    # Strict category filter
    filtered_rows = []
    filtered_out = 0
    for row in unique_rows:
        category = row.get("Category", "").strip().lower()
        if category and not any(tag in category for tag in ALLOWED_CATEGORIES):
            filtered_out += 1
            continue
        filtered_rows.append(row)
    unique_rows = filtered_rows
    print(f"[*] Filtered out {filtered_out} rows with irrelevant categories. Remaining: {len(unique_rows)}.")

    # Format phone numbers
    for row in unique_rows:
        phone = row.get("Phone", "").strip()
        while phone.startswith("'"):
            phone = phone[1:]
        row["Phone"] = f"'{phone}" if phone else ""

    # Sort: entries with website first
    unique_rows.sort(key=lambda r: (
        0 if normalize_website(r.get("Website", "")) else 1,
        normalize_website(r.get("Website", ""))
    ))

    # Write back
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
