import os

# ============================================================
#  Greece Labor Brokers & Recruitment Agencies - Google Maps Scraper
# ============================================================

# Google Maps Search Keywords (Greek employment agency tags)
KEYWORDS = [
    "Εταιρεία συμβουλευτικών υπηρεσιών ανθρώπινου δυναμικού",
    "Γραφείο εύρεσης προσωπικού",
    "Γραφείο απασχόλησης"
]

# Strict category filter - only keep if tag matches one of these (lowercased)
ALLOWED_CATEGORIES = {
    "εταιρεία συμβουλευτικών υπηρεσιών ανθρώπινου δυναμικού",
    "γραφείο εύρεσης προσωπικού",
    "γραφείο απασχόλησης"
}

# Vietnamese translations for categories
CATEGORY_TRANSLATIONS = {
    "εταιρεία συμβουλευτικών υπηρεσιών ανθρώπινου δυναμικού": "Công ty tư vấn nhân sự",
    "γραφείο εύρεσης προσωπικού": "Văn phòng tuyển dụng / tìm kiếm nhân sự",
    "γραφείο απασχόλησης": "Văn phòng giới thiệu việc làm"
}

# Output settings
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_CSV = os.path.join(os.path.dirname(SCRIPT_DIR), "broker_greece.csv")
PROGRESS_FILE = os.path.join(os.path.dirname(os.path.dirname(OUTPUT_CSV)), "progress", "scraping_progress_broker_gr.json")

# Playwright Browser Settings
HEADLESS = False  # Set to True to run browser hidden
SLOW_MO = 5       # ms delay between Playwright actions
TIMEOUT = 60000   # 60 seconds

# Search delay (seconds) — between 0.1–0.4 per result
MIN_DELAY = 0.1
MAX_DELAY = 0.4

# Google Maps CSS Selectors
SELECTORS = {
    "results_container": 'div[role="feed"]',
    "listing_link":      'a.hfpxzc',
    "business_name":     'h1.DUwDvf',
    "website":           'a[data-item-id="authority"]',
    "phone":             'button[data-item-id^="phone:tel:"]',
    "address":           'button[data-item-id^="address"]',
    "rating":            'div.F7nice span[aria-hidden="true"]',
    "reviews_count":     'div.F7nice span[aria-label*="reviews"]',
    "category":          'span.mgr77e, button.DkEaCc, button.DkEaL, button[jsaction*="category"], [jsaction*="category"], div.F7nice ~ span, div.F7nice ~ button',
}
