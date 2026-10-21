# -*- coding: utf-8 -*-
import sys
import json
import urllib.parse
from curl_cffi import requests
from bs4 import BeautifulSoup

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

session = requests.Session(impersonate="chrome120")
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}

print("=== 1. TEST WORK24 ===")
kw_w24 = urllib.parse.quote("선박 용접")
url_w24 = f"https://www.work24.go.kr/wk/a/b/1200/retriveDtlEmpSrchList.do?srcKeyword={kw_w24}"
try:
    r = session.get(url_w24, headers=headers, timeout=10)
    print("Work24 status:", r.status_code, "length:", len(r.text))
    soup = BeautifulSoup(r.text, "html.parser")
    # Work24 table tbody tr
    trs = soup.select("table.board-list tbody tr") or soup.select("tbody tr")
    print("Work24 tr found:", len(trs))
    for tr in trs[:5]:
        tds = tr.find_all("td")
        if len(tds) >= 4:
            comp = tds[0].text.strip().replace("\n", " ")
            tit = tds[1].text.strip().replace("\n", " ")
            print(f" -> Comp: {comp[:30]} | Tit: {tit[:40]}")
except Exception as e:
    print("Work24 error:", e)

print("\n=== 2. TEST SARAMIN ===")
kw_srm = urllib.parse.quote("선박 용접")
url_srm = f"https://www.saramin.co.kr/zf_user/search?searchword={kw_srm}"
try:
    r = session.get(url_srm, headers=headers, timeout=10)
    print("Saramin status:", r.status_code, "length:", len(r.text))
    soup = BeautifulSoup(r.text, "html.parser")
    items = soup.select("div.item_recruit")
    print("Saramin item_recruit found:", len(items))
    for it in items[:5]:
        corp = it.select_one("div.area_corp strong.corp_name a") or it.select_one("strong.corp_name")
        tit = it.select_one("h2.job_tit a") or it.select_one("h2.job_tit")
        loc = it.select_one("div.job_condition span")
        print(f" -> Corp: {corp.text.strip() if corp else ''} | Tit: {tit.text.strip() if tit else ''} | Loc: {loc.text.strip() if loc else ''}")
except Exception as e:
    print("Saramin error:", e)

print("\n=== 3. TEST JOBKOREA ===")
kw_jk = urllib.parse.quote("선박 용접")
url_jk = f"https://www.jobkorea.co.kr/Search/?stext={kw_jk}"
try:
    r = session.get(url_jk, headers=headers, timeout=10)
    print("JobKorea status:", r.status_code, "length:", len(r.text))
    soup = BeautifulSoup(r.text, "html.parser")
    items = soup.select("article.list-item") or soup.select("li.list-post")
    print("JobKorea items found:", len(items))
    for it in items[:5]:
        corp = it.select_one("div.post-list-corp a") or it.select_one("a.name")
        tit = it.select_one("div.post-list-info a.title") or it.select_one("a.title")
        print(f" -> Corp: {corp.text.strip() if corp else ''} | Tit: {tit.text.strip() if tit else ''}")
except Exception as e:
    print("JobKorea error:", e)
