import csv
import glob
import os
import sys

# Set console output encoding to UTF-8
if sys.platform.startswith('win'):
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

def safe_print(msg):
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        try:
            print(msg.encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8'), flush=True)
        except Exception:
            print(msg.encode('ascii', errors='replace').decode('ascii'), flush=True)

def format_phones_in_file(file_path, phone_col):
    if not os.path.exists(file_path):
        safe_print(f"[-] File not found: {file_path}")
        return
        
    safe_print(f"[*] Formatting phone numbers in: {os.path.basename(file_path).encode('ascii', errors='replace').decode('ascii')}")
    
    with open(file_path, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
        
    if phone_col not in fieldnames:
        safe_print(f"  [-] Column '{phone_col}' not found in headers!")
        return
        
    formatted_count = 0
    for row in rows:
        phone = row.get(phone_col, "")
        if phone and not phone.startswith("'"):
            row[phone_col] = f"'{phone}"
            formatted_count += 1
            
    if formatted_count > 0:
        temp_path = file_path + ".tmp"
        with open(temp_path, mode='w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        if os.path.exists(file_path):
            os.remove(file_path)
        os.rename(temp_path, file_path)
        safe_print(f"  [+] Successfully formatted {formatted_count} phone numbers!")
    else:
        safe_print("  [+] No formatting needed. All phone numbers already start with a single quote.")

def main():
    # 1. Clean Ireland files
    # The phone column is 'SĐT'
    ireland_files = glob.glob("*(ch*)*ireland*CleanData.csv")
    for f_path in ireland_files:
        format_phones_in_file(f_path, "SĐT")
        
    # 2. Clean Korean Agencies file
    # The phone column is 'Số điện thoại / Phone'
    korean_files = glob.glob("*korean_agencies.csv")
    for f_path in korean_files:
        format_phones_in_file(f_path, "Số điện thoại / Phone")

if __name__ == "__main__":
    main()
