import os

# Google Maps Search Settings (Greece Hotels & Accommodations)
KEYWORDS = [
    "Ξενοδοχείο 5 αστέρων",
    "Κατ' οίκον φιλοξενία",
    "Ξενοδοχείο",
    "Ξενοδοχείο 4 αστέρων",
    "Ξενοδοχείο 3 αστέρων",
    "Ξενοδοχείο 2 αστέρων",
    "Ξενοδοχείο 1 αστέρων",
    "Ξενοδοχείο παρατεταμένης διαμονής",
    "Χόστελ",
    "Μοτέλ"
]

# Allowed Greek Category Tags for strict filtering
ALLOWED_CATEGORIES = {
    "ξενοδοχείο 5 αστέρων",
    "κατ' οίκον φιλοξενία",
    "ξενοδοχείο",
    "ξενοδοχείο 4 αστέρων",
    "ξενοδοχείο 3 αστέρων",
    "ξενοδοχείο 2 αστέρων",
    "ξενοδοχείο 1 αστέρων",
    "ξενοδοχείο παρατεταμένης διαμονής",
    "χόστελ",
    "μοτέλ"
}

# Output settings (uses dynamic relative paths)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_CSV = os.path.join(os.path.dirname(SCRIPT_DIR), "hotel_greece.csv")
PROGRESS_FILE = os.path.join(os.path.dirname(OUTPUT_CSV), "scraping_progress_hotel_gr.json")

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
    "reviews_count": 'div.F7nice span[aria-label*="reviews"]',
    "category": 'span.mgr77e, button.DkEaCc, button.DkEaL, div.F7nice ~ span, div.F7nice ~ button',
}
