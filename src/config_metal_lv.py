import os

# ============================================================
#  Latvia Metal Fabrication / Metalworking - Google Maps Scraper
#  Tag chính: Metāla darbnīca (Metal workshop)
# ============================================================

# Google Maps Search Keywords (Latvian metalworking tags)
KEYWORDS = [
    "Metāla darbnīca",
    "Metālapstrāde",
    "Metāla konstrukcijas",
    "Metāla izstrādājumu ražotājs",
    "Metāllūžņu sniedzējs"
]

# Strict category filter - only keep if tag matches one of these
ALLOWED_CATEGORIES = {
    "metāla darbnīca",
    "metālapstrāde",
    "metāla konstrukcijas",
    "metāla izstrādājumu ražotājs",
    "metāllūžņu sniedzējs",
    "metālapstrādes uzņēmums",
    "metālizstrādājumu ražotājs",
    "metāla ražotājs",
    "nerūsejošā tērauda piegādātājs",
    "tērauda piegādātājs",
    "metāla jumts",
    "metāla detaļu ražotājs",
    "metālapstrādes pakalpojumi"
}

# Vietnamese translations for categories
CATEGORY_TRANSLATIONS = {
    "metāla darbnīca":               "Xưởng gia công kim loại",
    "metālapstrāde":                 "Gia công kim loại",
    "metāla konstrukcijas":          "Kết cấu kim loại",
    "metāla izstrādājumu ražotājs":  "Nhà sản xuất sản phẩm kim loại",
    "metāllūžņu sniedzējs":          "Nhà cung cấp phế liệu kim loại",
    "metālapstrādes uzņēmums":       "Công ty gia công kim loại",
    "metālizstrādājumu ražotājs":    "Nhà sản xuất đồ kim loại",
    "metāla ražotājs":               "Nhà sản xuất kim loại",
    "nerūsejošā tērauda piegādātājs":"Nhà cung cấp thép không gỉ",
    "tērauda piegādātājs":           "Nhà cung cấp thép",
    "metāla jumts":                  "Mái kim loại",
    "metāla detaļu ražotājs":        "Nhà sản xuất phụ tùng kim loại",
    "metālapstrādes pakalpojumi":    "Dịch vụ gia công kim loại",
}

# Output settings
OUTPUT_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw", "metal_latvia.csv")
PROGRESS_FILE = os.path.join(os.path.dirname(os.path.dirname(OUTPUT_CSV)), "progress", "scraping_progress_metal_lv.json")

# Playwright Browser Settings
HEADLESS = False   # Set to True to run browser hidden
SLOW_MO  = 5       # ms delay between Playwright actions
TIMEOUT  = 60000   # 60 seconds

# Search delay (seconds) — between 0.1–0.4 per result
MIN_DELAY = 0.1
MAX_DELAY = 0.4

# Google Maps CSS Selectors
SELECTORS = {
    "results_container": "div[role=\"feed\"]",
    "listing_link":      "a.hfpxzc",
    "business_name":     "h1.DUwDvf",
    "website":           "a[data-item-id=\"authority\"]",
    "phone":             "button[data-item-id^=\"phone:tel:\"]",
    "address":           "button[data-item-id^=\"address\"]",
    "rating":            "div.F7nice span[aria-hidden=\"true\"]",
    "reviews_count":     "div.F7nice span[aria-label*=\"reviews\"]",
    "category":          "button.DkEaCc, button.DkEaL, button[jsaction*=\"category\"], [jsaction*=\"category\"]",
}
