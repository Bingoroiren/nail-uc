# -*- coding: utf-8 -*-
import asyncio
import re
import sys
from curl_cffi.requests import AsyncSession

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,7}\b')

async def test_fb():
    fb_url = "https://www.facebook.com/biovela.lt/"
    print(f"[+] Testing Facebook URL: {fb_url}")
    try:
        async with AsyncSession(impersonate='chrome124') as s:
            r = await s.get(fb_url, timeout=10)
            print("  Status:", r.status_code)
            emails = set(EMAIL_REGEX.findall(r.text))
            valid = [e for e in emails if not e.endswith(('.png', '.jpg', '.webp', '.svg')) and 'facebook' not in e and 'fb.com' not in e]
            print("  Emails found:", valid)
    except Exception as e:
        print("  Error:", e)

if __name__ == '__main__':
    asyncio.run(test_fb())
