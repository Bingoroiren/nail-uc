import os
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
import re

with open(os.path.join(ROOT_DIR, "data", "assets", "suhyup_list.html"), "r", encoding="utf-8") as f:
    text = f.read()

print("Total length:", len(text))
print("Found script tags:", len(re.findall(r'<script', text, re.I)))
print("Found table tags:", len(re.findall(r'<table', text, re.I)))
print("Found td tags:", len(re.findall(r'<td', text, re.I)))

# Find any URLs containing .do or .json or .php or .xls
urls = re.findall(r'["\'\s\(=]([^\'"\s\(\)=]*?\.(?:do|json|php|xls|xlsx|csv)(?:\?[^\'"\s]*)?)["\'\s\)]', text)
print("Found URLs:", len(urls))
for u in sorted(list(set(urls)))[:50]:
    print("URL:", u)
