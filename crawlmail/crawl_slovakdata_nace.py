"""
Crawl SlovakData.sk by NACE code via API
Outputs 3 raw CSV files:
- SK_MECH_SLVD_0RAW.csv (NACE 28 - Cơ khí / Chế tạo máy)
- SK_AUTO_SLVD_0RAW.csv (NACE 29 - Ô tô / Phương tiện cơ giới)
- SK_MTAL_SLVD_0RAW.csv (NACE 25 - Gia công kim loại)
"""

import sys
import os
import time
import csv
from curl_cffi import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

TARGET_CONFIGS = [
    {
        "nace": "28",
        "category_vn": "Cơ khí / Chế tạo máy móc (NACE 28)",
        "output_file": "SK_MECH_SLVD_0RAW.csv",
        "description": "NACE 28: Výroba strojov a zariadení (Cơ khí / Máy móc)",
    },
    {
        "nace": "29",
        "category_vn": "Sản xuất Ô tô / Xe cơ giới (NACE 29)",
        "output_file": "SK_AUTO_SLVD_0RAW.csv",
        "description": "NACE 29: Výroba motorových vozidiel (Ô tô / Phụ tùng xe)",
    },
    {
        "nace": "25",
        "category_vn": "Gia công kim loại / Kết cấu (NACE 25)",
        "output_file": "SK_MTAL_SLVD_0RAW.csv",
        "description": "NACE 25: Výroba kovových konštrukcií a kovových výrobkov (Gia công kim loại)",
    },
]

HEADERS = [
    "No.",
    "Công ty",
    "IČO",
    "SĐT",
    "Web",
    "Email",
    "Địa chỉ",
    "Thành phố",
    "Mã bưu điện",
    "NACE",
    "NACE Popis",
    "Loại hình",
    "Quy mô nhân sự",
    "Doanh thu (EUR)",
    "Lợi nhuận (EUR)",
    "Năm tài chính",
    "Ngày thành lập",
    "Độ uy tín thuế",
    "Category",
    "Source",
]


def build_address(it):
    ulice = (it.get("ulice_text") or "").strip()
    cdom = str(it.get("cdom") or "").strip()
    cor = str(it.get("cor") or "").strip()
    obec = (it.get("obec_text") or "").strip()
    psc = (it.get("psc") or "").strip()

    num = ""
    if cor and cor != "0" and cdom and cdom != "0":
        num = f"{cdom}/{cor}"
    elif cor and cor != "0":
        num = cor
    elif cdom and cdom != "0":
        num = cdom

    street_part = ""
    if ulice:
        street_part = f"{ulice} {num}".strip() if num else ulice
    elif obec:
        street_part = f"{obec} {num}".strip() if num else obec

    parts = []
    if street_part:
        parts.append(street_part)
    if psc and obec:
        parts.append(f"{psc} {obec}")
    elif obec:
        parts.append(obec)
    elif psc:
        parts.append(psc)
    parts.append("Slovensko")

    return ", ".join(parts)


def crawl_nace(cfg, limit=500):
    nace = cfg["nace"]
    cat_vn = cfg["category_vn"]
    out_file = cfg["output_file"]
    desc = cfg["description"]

    print(f"\n==================================================")
    print(f"[*] Bắt đầu cào: {desc}")
    print(f"[*] Tệp xuất: {out_file}")
    print(f"==================================================")

    # 1. Fetch total count
    url_init = f"https://slovakdata.sk/api/search?nace={nace}&limit=1&page=1"
    try:
        r = requests.get(url_init, impersonate="chrome120", timeout=15)
        res_data = r.json()
        total_items = res_data.get("total", 0)
    except Exception as e:
        print(f"[-] Lỗi khi kết nối ban đầu: {e}")
        return

    total_pages = (total_items + limit - 1) // limit
    print(f"[*] Tổng số bản ghi tìm thấy: {total_items:,} ({total_pages} trang)")

    # Prepare file
    with open(out_file, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(HEADERS)

    count_saved = 0
    count_skipped_inactive = 0
    seen_icos = set()

    for page in range(1, total_pages + 1):
        page_url = f"https://slovakdata.sk/api/search?nace={nace}&limit={limit}&page={page}"
        success = False
        items = []

        for attempt in range(3):
            try:
                resp = requests.get(page_url, impersonate="chrome120", timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("results", [])
                    success = True
                    break
                else:
                    print(f"    [!] Trang {page} status {resp.status_code}, thử lại lần {attempt + 1}...")
                    time.sleep(2)
            except Exception as ex:
                print(f"    [!] Trang {page} ngoại lệ: {ex}, thử lại lần {attempt + 1}...")
                time.sleep(2)

        if not success or not items:
            print(f"[-] Bỏ qua trang {page} do không lấy được dữ liệu sau 3 lần thử.")
            continue

        rows_to_write = []
        for it in items:
            ico = str(it.get("ico") or "").strip()
            if not ico or ico in seen_icos:
                continue

            # Check if active
            ddatzan = it.get("ddatzan")
            pozastavena = it.get("pozastavena")
            konkurz = it.get("konkurz_druh")

            if ddatzan or pozastavena or konkurz:
                count_skipped_inactive += 1
                continue

            seen_icos.add(ico)
            count_saved += 1

            firma = (it.get("firma") or "").strip()
            addr = build_address(it)
            city = (it.get("obec_text") or "").strip()
            psc = (it.get("psc") or "").strip()
            sub_nace = str(it.get("nace") or "").strip()
            nace_desc = (it.get("nace_text") or "").strip()
            forma = (it.get("forma_text") or "").strip()
            katpo = (it.get("katpo_text") or "").strip()
            trzby = it.get("trzby")
            vysledok = it.get("vysledok")
            fin_rok = it.get("fin_rok") or ""
            ddatvzn = str(it.get("ddatvzn") or "")[:10]
            index_ds = (it.get("index_ds") or "").strip()

            row = [
                count_saved,
                firma,
                ico,
                "",  # SĐT (chưa có)
                "",  # Web
                "",  # Email
                addr,
                city,
                psc,
                sub_nace,
                nace_desc,
                forma,
                katpo,
                f"{trzby:,}" if isinstance(trzby, (int, float)) else (trzby or ""),
                f"{vysledok:,}" if isinstance(vysledok, (int, float)) else (vysledok or ""),
                fin_rok,
                ddatvzn,
                index_ds,
                cat_vn,
                "slovakdata.sk",
            ]
            rows_to_write.append(row)

        with open(out_file, "a", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(rows_to_write)

        print(f"    [+] Trang {page}/{total_pages}: +{len(rows_to_write)} cty hoạt động (Lũy kế: {count_saved:,} cty, Đã lọc bỏ: {count_skipped_inactive} cty ngưng/giải thể)")
        time.sleep(0.4)

    print(f"[V] Hoàn tất NACE {nace}: Đã lưu {count_saved:,} doanh nghiệp đang hoạt động vào {out_file}\n")


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "all"

    for cfg in TARGET_CONFIGS:
        if target == "all" or target == cfg["nace"]:
            crawl_nace(cfg)


if __name__ == "__main__":
    main()
