# -*- coding: utf-8 -*-
"""
Cấu hình Bộ Cào Doanh Nghiệp Chế Biến Thực Phẩm & Ngành Thực Phẩm Litva (Lithuania)
trên Google Maps (hl=lt, zoom 10/11)
"""

import os

# Đường dẫn thư mục gốc tương đối (đảm bảo đẩy lên Git và chạy trên mọi máy)
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SRC_DIR)

# File dữ liệu xuất
OUTPUT_CSV = os.path.join(BASE_DIR, "data", "raw", "thuc_pham_litva_maps.csv")
OUTPUT_XLSX = os.path.join(BASE_DIR, "data", "raw", "thuc_pham_litva_maps.xlsx")

# File tiến trình cào & cache email
PROGRESS_FILE = os.path.join(BASE_DIR, "data", "progress", "scraping_progress_thuc_pham_lt.json")
EMAIL_CACHE_FILE = os.path.join(BASE_DIR, "data", "progress", "cache_emails_thuc_pham_lt.json")

# File dữ liệu cũ để lọc trùng (nếu công ty đã có email thì bỏ qua)
EXISTING_REKVIZITAI_CSV = os.path.join(BASE_DIR, "chế biến thực phẩm litva - đã làm giàu rekvizitai.csv")
EXISTING_EMAIL_CACHE = os.path.join(BASE_DIR, "crawlmail", "cache_emails_thuc_pham_litva.json")

# Danh sách 22 Tag ngành nghề tiếng Lithuania theo yêu cầu của bạn:
TAG_TRANSLATIONS = {
    "maisto produktų gamintojas": "Nhà sản xuất sản phẩm thực phẩm",
    "maisto perdirbimo įmonė": "Doanh nghiệp / Nhà máy chế biến thực phẩm",
    "žuvies perdirbimo įmonė": "Cơ sở / Nhà máy chế biến cá & thủy sản",
    "maisto gamintojas": "Nhà sản xuất thực phẩm",
    "šaldytų maisto produktų gamintojas": "Nhà sản xuất thực phẩm đông lạnh",
    "konservų fabrikas": "Nhà máy đồ hộp / đóng hộp",
    "maisto prieskonių gamintojas": "Nhà sản xuất gia vị thực phẩm",
    "skerdykla": "Lò giết mổ gia súc / gia cầm",
    "mėsos pakuotojas": "Cơ sở đóng gói thịt",
    "cechas": "Phân xưởng / Xưởng sản xuất chế biến",
    "pieninė": "Nhà máy sữa / Cơ sở chế biến sữa",
    "makaronų parduotuvė": "Cửa hàng / Xưởng sản xuất mì & nui",
    "mėsos gaminių didmenininkas": "Nhà bán buôn sản phẩm từ thịt",
    "pieno produktų tiekėjas": "Nhà cung cấp sản phẩm từ sữa",
    "maisto produktų tiekėjas": "Nhà cung cấp sản phẩm thực phẩm",
    "šaldoma saugykla": "Kho lạnh bảo quản",
    "jūros gėrybių didmenininkas": "Nhà bán buôn hải sản",
    "produktų didmenininkas": "Nhà bán buôn sản phẩm / hàng thực phẩm",
    "kepyklos gaminių didmenininkas": "Nhà bán buôn sản phẩm bánh mì / bánh ngọt",
    "alaus platintojas": "Nhà phân phối bia",
    "mėsos parduotuvė": "Cửa hàng thịt tươi",
    "žuvies parduotuvė": "Cửa hàng cá & thủy sản",
}

# Danh sách từ khóa tìm kiếm trên Google Maps (nguyên bản chữ hoa chuẩn tiếng Lithuania)
KEYWORDS = [
    "Maisto produktų gamintojas",
    "Maisto perdirbimo įmonė",
    "Žuvies perdirbimo įmonė",
    "Maisto gamintojas",
    "Šaldytų maisto produktų gamintojas",
    "Konservų fabrikas",
    "Maisto prieskonių gamintojas",
    "Skerdykla",
    "Mėsos pakuotojas",
    "Cechas",
    "Pieninė",
    "Makaronų parduotuvė",
    "Mėsos gaminių didmenininkas",
    "Pieno produktų tiekėjas",
    "Maisto produktų tiekėjas",
    "Šaldoma saugykla",
    "Jūros gėrybių didmenininkas",
    "Produktų didmenininkas",
    "Kepyklos gaminių didmenininkas",
    "Alaus platintojas",
    "Mėsos parduotuvė",
    "Žuvies parduotuvė",
]

# Bộ lọc tag nghiêm ngặt (chỉ chấp nhận các tag nằm trong danh sách này)
ALLOWED_CATEGORIES = set(TAG_TRANSLATIONS.keys())

# Cấu hình Trình duyệt (Chrome, zoom 11, ngôn ngữ tiếng Lithuania)
HEADLESS = False     # Hiển thị trình duyệt để người dùng theo dõi
ZOOM_LEVEL = 11      # Mức zoom bản đồ (10 hoặc 11)
MAPS_LANG = "lt"     # Ngôn ngữ giao diện Google Maps (Lithuanian)
TIMEOUT = 45000      # Timeout tải trang (ms)

# Các selector chuẩn của Google Maps
SELECTORS = {
    "results_container": 'div[role="feed"]',
    "listing_link": 'a.hfpxzc',
    "business_name": 'h1.DUwDvf',
    "website": 'a[data-item-id="authority"]',
    "phone": 'button[data-item-id^="phone:tel:"]',
    "address": 'button[data-item-id^="address"]',
    "rating": 'div.F7nice span[aria-hidden="true"]',
    "reviews_count": 'div.F7nice span[aria-label*="reviews"], div.F7nice span[aria-label*="atsiliepim"], div.F7nice span[aria-label*="atsauksm"]',
    "category": 'button.DkEaCc, button.DkEaL, button[jsaction*="category"], [jsaction*="category"]',
}
