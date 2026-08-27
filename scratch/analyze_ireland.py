import csv
import glob
import os
import re

def safe_encode(s):
    return s.encode('ascii', errors='replace').decode('ascii')

def main():
    # Find file matching pattern
    files = glob.glob("*(ch*M*gi*ireland*CleanData.csv")
    if not files:
        # Try finding by simpler pattern
        files = glob.glob("*ireland - CleanData.csv")
        
    if not files:
        print("[-] Ireland CSV file not found.")
        return
        
    file_path = files[0]
    print(f"[+] Found file: {safe_encode(file_path)}")
    
    with open(file_path, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
        
    print(f"\n--- Fieldnames in CSV ---")
    for fn in fieldnames:
        print(f"  {safe_encode(fn)}")
        
    total_rows = len(rows)
    empty_emails = 0
    spam_directory_websites = 0
    valid_websites_no_email = 0
    
    # We want to identify the columns for Company, Website (usually 'Liên Hệ' or 'Liên hệ')
    company_col = 'Công ty'
    website_col = 'Liên Hệ' # From our previous view, it is 'Liên Hệ'
    email_col = 'Email'
    
    junk_domains = ["lunarcarpentry.vip", "galwaymusiccircle.vip", "irishdbmap.com", "irishdbmap.work", "irelanddbmap", "vi.vip", "musiccircle", "carpentry.vip"]
    
    no_email_sample = []
    
    for idx, row in enumerate(rows, 1):
        comp = row.get(company_col, "")
        web = row.get(website_col, "")
        email = row.get(email_col, "")
        
        is_empty_email = not email.strip()
        if is_empty_email:
            empty_emails += 1
            
        is_junk_web = False
        if web:
            for jd in junk_domains:
                if jd in web.lower():
                    is_junk_web = True
                    break
        
        if is_junk_web:
            spam_directory_websites += 1
            
        if is_empty_email and web and not is_junk_web:
            valid_websites_no_email += 1
            if len(no_email_sample) < 10:
                no_email_sample.append((comp, web))
                
    print(f"\nTotal rows in CSV: {total_rows}")
    print(f"Rows with empty email: {empty_emails}")
    print(f"Rows with spam directory website (lunarcarpentry, galwaymusiccircle, etc.): {spam_directory_websites}")
    print(f"Rows with valid website but empty email: {valid_websites_no_email}")
    
    print("\n--- Sample of rows with valid website but empty email ---")
    for comp, web in no_email_sample:
        print(f"  Company: {safe_encode(comp)} -> Website: {safe_encode(web)}")

if __name__ == "__main__":
    main()
