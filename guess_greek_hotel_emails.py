import csv
import os
import re
import urllib.parse
import sys

# Set console output encoding to UTF-8
if sys.platform.startswith('win'):
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

FILE_PATH = "(chờ) khách sạn Hy Lạp - CleanData.csv"

SOCIAL_DOMAINS = {
    # Social networks & Media
    'facebook.com', 'fb.com', 'fb.me',
    'instagram.com', 'instagr.am',
    'twitter.com', 'x.com',
    'linkedin.com',
    'youtube.com', 'youtu.be',
    'tiktok.com',
    'pinterest.com', 'pin.it',
    'reddit.com',
    'threads.net',
    'tumblr.com',
    'flickr.com',
    'snapchat.com',
    # Messaging
    't.me', 'telegram.org', 'telegram.me',
    'wa.me', 'whatsapp.com',
    'line.me',
    'viber.com',
    'zalo.me',
    'wechat.com',
    # Search & Maps
    'google.com', 'goo.gl', 'google.co.uk', 'google.ie', 'google.com.au',
    'google.com.tw', 'google.gr', 'google.pt', 'google.sk', 'google.lv',
    'google.co.nz', 'google.com.hk', 'google.de', 'google.fr',
    'maps.app.goo.gl', 'waze.com', 'bing.com', 'yahoo.com', 'duckduckgo.com',
    # Directories & Reviews & Platforms
    'yelp.com', 'yelp.com.au', 'yelp.ie', 'yelp.co.uk',
    'tripadvisor.com', 'tripadvisor.ie', 'tripadvisor.co.uk', 'tripadvisor.com.tw', 'tripadvisor.com.gr',
    'yellowpages.com', 'yellowpages.com.au', 'whitepages.com', 'whitepages.com.au',
    'foursquare.com', 'trustpilot.com', 'wikipedia.org', 'wikidata.org',
    # Website builders default / generic hosting
    'apple.com', 'apps.apple.com', 'play.google.com',
    'wix.com', 'wixsite.com', 'wixpress.com', 'squarespace.com', 
    'wordpress.com', 'weebly.com', 'site123.me', 'jimdosite.com', 
    'godaddysites.com', 'myshopify.com', 'canva.site', 'linktr.ee', 'carrd.co'
}

def guess_email_from_website(website_url):
    if not website_url or not isinstance(website_url, str):
        return ""
    url = website_url.strip()
    if not url:
        return ""
    if not url.startswith(('http://', 'https://')):
        url = 'http://' + url
    try:
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc.strip().lower()
        if not netloc:
            return ""
        if ':' in netloc:
            netloc = netloc.split(':')[0]
        netloc = re.sub(r'^www\d*\.', '', netloc)
        if not netloc or '.' not in netloc:
            return ""
        for social in SOCIAL_DOMAINS:
            if netloc == social or netloc.endswith('.' + social):
                return ""
        if re.match(r'^[a-z0-9][a-z0-9\.\-]*\.[a-z]{2,}$', netloc):
            if netloc.endswith('.') or re.match(r'^\d+\.\d+\.\d+\.\d+$', netloc):
                return ""
            return f"info@{netloc}"
        return ""
    except Exception:
        return ""

def main():
    if not os.path.exists(FILE_PATH):
        print(f"[-] Error: File not found: {FILE_PATH}")
        return

    print(f"[*] Reading {FILE_PATH}...")
    with open(FILE_PATH, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    print(f"[+] Loaded {len(rows)} rows.")

    total_missing = 0
    guessed_count = 0
    phone_formatted_count = 0

    for idx, row in enumerate(rows, 1):
        email = (row.get("Email") or "").strip()
        
        if not email:
            total_missing += 1
            website = (row.get("Liên Hệ") or "").strip()
            
            if website:
                guessed = guess_email_from_website(website)
                if guessed:
                    row["Email"] = guessed
                    guessed_count += 1
        
        # Phone number prefix logic
        phone = (row.get("SĐT") or "").strip()
        if phone and not phone.startswith("'"):
            # Also clean spaces/brackets/dashes or just prefix the raw value
            row["SĐT"] = f"'{phone}"
            phone_formatted_count += 1

    print(f"[*] Total rows missing email: {total_missing}")
    print(f"[+] Successfully guessed email for: {guessed_count} rows")
    print(f"[+] Successfully formatted phone numbers (added single quote): {phone_formatted_count} rows")

    if guessed_count > 0 or phone_formatted_count > 0:
        print(f"[*] Saving changes back to {FILE_PATH}...")
        with open(FILE_PATH, mode="w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print("[SUCCESS] CSV updated successfully!")
    else:
        print("[*] No changes were made.")

if __name__ == "__main__":
    main()
