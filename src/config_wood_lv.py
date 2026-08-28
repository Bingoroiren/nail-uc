import os

# ============================================================
#  Latvia Woodworking / Carpentry - Google Maps Scraper
# ============================================================

# Google Maps Search Keywords (Latvian woodworking tags)
KEYWORDS = [
    "Galdniecība",
    "Mēbeļu izgatavotājs",
    "Galdnieks",
    "Kokmateriālu piegādātājs",
    "Kokzāģētava"
]

# Strict category filter - only keep if tag matches one of these
ALLOWED_CATEGORIES = {
    "galdniecība",
    "mēbeļu izgatavotājs",
    "galdnieks",
    "kokmateriālu piegādātājs",
    "kokzāģētava"
}

# Vietnamese translations for categories
CATEGORY_TRANSLATIONS = {
    "galdniecība":               "Xưởng mộc",
    "mēbeļu izgatavotājs":        "Nhà sản xuất đồ nội thất gỗ",
    "galdnieks":                  "Thợ mộc",
    "kokmateriālu piegādātājs":   "Nhà cung cấp gỗ",
    "kokzāģētava":                "Xưởng cưa gỗ",
}

# Output settings
OUTPUT_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw", "wood_latvia.csv")
PROGRESS_FILE = os.path.join(os.path.dirname(os.path.dirname(OUTPUT_CSV)), "progress", "scraping_progress_wood_lv.json")

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
