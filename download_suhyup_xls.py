import requests
import urllib3
import os
urllib3.disable_warnings()

url = "https://www.suhyup.co.kr/sites/suhyup/down/MembersCombination.xls"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.suhyup.co.kr/suhyup/193/subview.do"
}

output_file = "suhyup_coops.xls"

print(f"[*] Downloading Suhyup cooperatives Excel from {url}...")
try:
    response = requests.get(url, headers=headers, verify=False, timeout=20)
    if response.status_code == 200:
        with open(output_file, "wb") as f:
            f.write(response.content)
        print(f"[+] Successfully downloaded Suhyup member directory to: {os.path.abspath(output_file)}")
        print(f"[+] File size: {len(response.content)} bytes")
    else:
        print(f"[-] Failed to download. Status code: {response.status_code}")
except Exception as e:
    print(f"[-] Error downloading file: {e}")
