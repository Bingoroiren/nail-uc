"""
Scraper for MASOC (Association of Mechanical Engineering and Metalworking Industries of Latvia)
Member Database: https://www.masoc.lv/en/members/member-database

Usage:
    python crawlmail/scrape_masoc.py

Output:
    masoc_members.csv  - All member data (name, website, phone, email, address)
"""

import urllib.request
import urllib.parse
import json
import csv
import re
import time
from html.parser import HTMLParser
from pathlib import Path

BASE_URL = "https://www.masoc.lv/en/members/member-database"
OUTPUT_FILE = "masoc_members.csv"


class HTMLStripper(HTMLParser):
    """Simple HTML tag stripper."""
    def __init__(self):
        super().__init__()
        self.reset()
        self.fed = []

    def handle_data(self, d):
        self.fed.append(d)

    def get_data(self):
        return " ".join(self.fed).strip()


def strip_html(text):
    s = HTMLStripper()
    s.feed(text)
    return s.get_data()


def parse_member_html(html_text):
    """
    Parse the HTML fragment returned by the AJAX call.
    Each member is a <li> element with name, website, phone, email, address.
    """
    members = []

    # Split into individual member blocks
    items = re.split(r'<li\s+itemscope\s+itemtype="http://schema\.org/Organization">', html_text)

    for item in items[1:]:  # skip first empty split
        member = {}

        # Extract name
        name_match = re.search(r'itemprop="name"[^>]*><a[^>]*>([^<]+)</a>', item)
        member["name"] = name_match.group(1).strip() if name_match else ""

        # Extract profile URL (member ID)
        id_match = re.search(r'href="/en/members/member-database/(\d+)"', item)
        member["member_id"] = id_match.group(1) if id_match else ""
        member["profile_url"] = f"https://www.masoc.lv/en/members/member-database/{member['member_id']}" if member["member_id"] else ""

        # Extract website
        website_match = re.search(r'itemprop="url"[^>]*><a[^>]*>([^<]+)</a>', item)
        member["website"] = website_match.group(1).strip() if website_match else ""

        # Extract phone
        phone_match = re.search(r'itemprop="telephone"[^>]*>([^<]+)<', item)
        member["phone"] = phone_match.group(1).strip() if phone_match else ""

        # Extract email
        email_match = re.search(r'itemprop="email"[^>]*>([^<]+)<', item)
        member["email"] = email_match.group(1).strip() if email_match else ""

        # Extract address
        address_match = re.search(r'itemprop="address"[^>]*>([^<]+)<', item)
        member["address"] = address_match.group(1).strip() if address_match else ""

        if member["name"]:
            members.append(member)

    return members


def fetch_all_members():
    """Fetch all members using the AJAX endpoint (no-limit mode)."""
    print(f"Fetching all members from {BASE_URL} ...")

    post_data = urllib.parse.urlencode({
        "act": "search",
        "page": "1",
        "no-limit": "1"  # Get all results without pagination
    })

    req = urllib.request.Request(
        BASE_URL,
        post_data.encode(),
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": BASE_URL,
        }
    )

    resp = urllib.request.urlopen(req, timeout=30)
    raw = resp.read().decode("utf-8")

    data = json.loads(raw)

    # Extract count from head
    head_text = strip_html(data.get("head", ""))
    print(f"Server says: {head_text}")

    # Parse member HTML
    html_content = data.get("html", "")
    # Unescape HTML entities from JSON
    html_content = html_content.replace("\\/", "/")

    members = parse_member_html(html_content)
    print(f"Parsed {len(members)} members.")

    return members


def save_to_csv(members, filepath):
    """Save member list to CSV."""
    if not members:
        print("No members to save.")
        return

    fieldnames = ["name", "email", "website", "phone", "address", "member_id", "profile_url"]

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(members)

    print(f"\nSaved {len(members)} members to: {filepath}")


def main():
    output_path = Path(OUTPUT_FILE)

    members = fetch_all_members()

    # Stats
    with_email = sum(1 for m in members if m["email"])
    with_website = sum(1 for m in members if m["website"])

    print(f"\n--- Summary ---")
    print(f"Total members: {len(members)}")
    print(f"With email:    {with_email}")
    print(f"With website:  {with_website}")

    save_to_csv(members, output_path)

    # Print sample
    print("\n--- Sample (first 5) ---")
    for m in members[:5]:
        print(f"  {m['name']}")
        print(f"    Email:   {m['email'] or '(none)'}")
        print(f"    Website: {m['website'] or '(none)'}")
        print(f"    Phone:   {m['phone'] or '(none)'}")
        print(f"    Address: {m['address'] or '(none)'}")
        print()


if __name__ == "__main__":
    main()
    # Auto-run formatter after scraping
    import subprocess, sys
    fmt_script = str(Path(__file__).parent.parent / "format_masoc_emails.py")
    if Path(fmt_script).exists():
        print("\n[*] Running formatter...")
        subprocess.run([sys.executable, fmt_script], check=True)

