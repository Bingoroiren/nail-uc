import csv
import glob
import os
import sys

# Set console output encoding to UTF-8
if sys.platform.startswith('win'):
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

JUNK_DOMAINS = [
    "lunarcarpentry.vip", "galwaymusiccircle.vip", "irishdbmap.com", 
    "irishdbmap.work", "irelanddbmap", "vi.vip", "musiccircle", "carpentry.vip"
]

def safe_print(msg):
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        try:
            print(msg.encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8'), flush=True)
        except Exception:
            print(msg.encode('ascii', errors='replace').decode('ascii'), flush=True)

def score_email(email):
    email = email.lower().strip()
    if "@" not in email:
        return 0
    username, domain = email.split("@", 1)
    
    if any(email.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.js', '.css']):
        return 0
        
    system_usernames = ['noreply', 'no-reply', 'donotreply', 'privacy', 'terms', 'cookies', 'gdpr', 'abuse', 'security', 'webmaster', 'sentry', 'admin']
    if username in system_usernames or any(x in username for x in ['no-reply', 'noreply', 'privacy']):
        return 0
        
    junk_domains = JUNK_DOMAINS + ['sentry.io', 'wix.com', 'wordpress', 'squarespace', 'weebly', 'godaddy', 'example.com', 'domain.com', 'placeholder', 'wixpress', 'wixsite']
    if any(jd in domain for jd in junk_domains) or 'sentry' in domain or 'wix' in domain:
        return 0
        
    return 10

def main():
    files = glob.glob("*(ch*)*ireland*CleanData.csv")
    if not files:
        safe_print("[-] CSV files not found.")
        return
        
    for file_path in files:
        safe_print(f"\n[*] Cleaning file: {os.path.basename(file_path).encode('ascii', errors='replace').decode('ascii')}")
        
        with open(file_path, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            rows = list(reader)
            
        cleaned_rows_count = 0
        
        for row in rows:
            email_str = row.get("Email", "")
            web_str = row.get("Liên Hệ", "")
            
            if not email_str:
                continue
                
            # Check if website is junk directory
            is_junk_web = web_str and any(jd in web_str.lower() for jd in JUNK_DOMAINS)
            
            emails = [x.strip() for x in email_str.split(",") if x.strip()]
            valid_emails = []
            
            for email in emails:
                score = score_email(email)
                if score >= 4 and not is_junk_web:
                    valid_emails.append(email)
                    
            new_email_str = ", ".join(valid_emails)
            if email_str != new_email_str:
                row["Email"] = new_email_str
                cleaned_rows_count += 1
                safe_print(f"  [Cleaned] Company: {row.get('Công ty', '')} -> Removed junk email: '{email_str}' -> Kept: '{new_email_str}'")
                
                # If the website was junk, clear it too to keep data pristine
                if is_junk_web:
                    row["Liên Hệ"] = ""
                    
        # Save back atomically
        if cleaned_rows_count > 0:
            temp_path = file_path + ".tmp"
            with open(temp_path, mode='w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            if os.path.exists(file_path):
                os.remove(file_path)
            os.rename(temp_path, file_path)
            safe_print(f"[+] Successfully cleaned {cleaned_rows_count} rows with spam or directory emails!")
        else:
            safe_print("[+] No spam emails found. Dataset is already clean!")

if __name__ == "__main__":
    main()
