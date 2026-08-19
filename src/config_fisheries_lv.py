import os

# Google Maps Search Settings (Latvia Fisheries / Seafood / Aquaculture)
KEYWORDS = [
    "Zivju apstrādes uzņēmums",
    "Konservu fabrika",
    "Zivju ferma",
    "Akvakultūras ferma",
    "Jūras velšu vairumtirgotājs"
]

# Allowed Latvian Category Tags for strict filtering
ALLOWED_CATEGORIES = {
    "zivju apstrādes uzņēmums",
    "konservu fabrika",
    "zivju ferma",
    "akvakultūras ferma",
    "jūras velšu vairumtirgotājs"
}

# Output settings
OUTPUT_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fisheries_latvia.csv")
PROGRESS_FILE = os.path.join(os.path.dirname(OUTPUT_CSV), "scraping_progress_fisheries_lv.json")

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
    "category": 'button.DkEaCc, button.DkEaL, button[jsaction*="category"], button[jsaction*="hotelclass"], [jsaction*="category"], [jsaction*="hotelclass"]',
}
