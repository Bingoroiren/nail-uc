import os

# Google Maps Search Settings (Canada Labor Recruitment / Employment Agencies)
KEYWORDS = [
    "Employment agency",
    "Temp agency",
    "Human resource consulting",
    "Recruiter",
    "Employment consultant"
]

# Allowed Category Tags for strict filtering (lowercase for comparison)
ALLOWED_CATEGORIES = {
    "employment agency",
    "temp agency",
    "human resource consulting",
    "recruiter",
    "employment consultant"
}

# Output settings
OUTPUT_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw", "broker_canada.csv")
PROGRESS_FILE = os.path.join(os.path.dirname(os.path.dirname(OUTPUT_CSV)), "progress", "scraping_progress_broker_ca.json")

# Playwright Browser Settings
HEADLESS = False
SLOW_MO = 5
TIMEOUT = 60000

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
