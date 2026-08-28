import os
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
import requests
import urllib3
urllib3.disable_warnings()

url = "https://www.suhyup.co.kr/suhyup/193/subview.do"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.suhyup.co.kr/"
}

try:
    response = requests.get(url, headers=headers, verify=False, timeout=15)
    with open(os.path.join(ROOT_DIR, "data", "assets", "suhyup_list.html"), "w", encoding="utf-8") as f:
        f.write(response.text)
    print(f"[+] Downloaded, status code: {response.status_code}, length: {len(response.text)}")
except Exception as e:
    print(f"[-] Error: {e}")
