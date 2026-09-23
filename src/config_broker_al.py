import os

# Google Maps Search Settings (Albania Labor Recruitment / Employment Agencies)
# 5 standard Albanian tags requested by the user
KEYWORDS = [
    "Shërbim konsulent për Burime Njerëzore",
    "Agjenci punësimi",
    "Qendra e punësimit",
    "Rekrutues",
    "Agjenci për punë të përkohshme"
]

# Allowed Albanian Category Tags for strict filtering (lowercase & normalized accents)
ALLOWED_CATEGORIES = {
    "shërbim konsulent për burime njerëzore",
    "sherbim konsulent per burime njerezore",
    "agjenci punësimi",
    "agjenci punesimi",
    "qendra e punësimit",
    "qendra e punesimit",
    "rekrutues",
    "agjenci për punë të përkohshme",
    "agjenci per pune te perkohshme"
}

# Category translations to Vietnamese for final formatting & reporting
CATEGORY_TRANSLATIONS = {
    "shërbim konsulent për burime njerëzore": "Dịch vụ tư vấn nhân sự",
    "sherbim konsulent per burime njerezore": "Dịch vụ tư vấn nhân sự",
    "agjenci punësimi": "Công ty môi giới việc làm",
    "agjenci punesimi": "Công ty môi giới việc làm",
    "qendra e punësimit": "Trung tâm dịch vụ việc làm",
    "qendra e punesimit": "Trung tâm dịch vụ việc làm",
    "rekrutues": "Nhà tuyển dụng / Săn đầu người",
    "agjenci për punë të përkohshme": "Công ty cung ứng lao động tạm thời",
    "agjenci per pune te perkohshme": "Công ty cung ứng lao động tạm thời"
}

# Dynamic File and Directory Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
DATA_FORMATTED_DIR = os.path.join(BASE_DIR, "data", "formatted")
PROGRESS_DIR = os.path.join(BASE_DIR, "progress")

OUTPUT_CSV = os.path.join(DATA_RAW_DIR, "broker_albania.csv")
PROGRESS_FILE = os.path.join(PROGRESS_DIR, "scraping_progress_broker_al.json")

# Map zoom level: 10 or 11 (default 11)
MAP_ZOOM = 11

# Playwright Browser Settings
HEADLESS = False  # Set to True to run the browser hidden in the background
SLOW_MO = 5       # Delay (ms) between actions
TIMEOUT = 60000   # Timeout for page loading and element matching (60 seconds)

# Delay Settings (Seconds)
MIN_DELAY = 0.1
MAX_DELAY = 0.4

# Google Maps Selectors
SELECTORS = {
    "results_container": 'div[role="feed"]',
    "listing_link": 'a.hfpxzc',
    "business_name": 'h1.DUwDvf',
    "website": 'a[data-item-id="authority"]',
    "phone": 'button[data-item-id^="phone:tel:"]',
    "address": 'button[data-item-id^="address"]',
    "rating": 'div.F7nice span[aria-hidden="true"]',
    "reviews_count": 'div.F7nice span[aria-label*="reviews"], div.F7nice span[aria-label*="vlerësime"], div.F7nice span[aria-label*="recensione"], div.F7nice span[aria-label*="review"]',
    "category": 'span.mgr77e, button.DkEaCc, button.DkEaL, div.F7nice ~ span, div.F7nice ~ button',
}
