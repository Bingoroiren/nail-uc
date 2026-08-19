import os

# Google Maps Search Settings (Portugal Hotels & Accommodations)
KEYWORDS = [
    "Hospedaria",
    "Hotel de 3 estrelas",
    "Hotel",
    "Hotel de 5 estrelas",
    "Hotel de 4 estrelas",
    "Hotel Resort",
    "Hospedagem domiciliar",
    "Hotel de 2 estrelas",
    "Albergue"
]

# Allowed Portuguese Category Tags for strict filtering
ALLOWED_CATEGORIES = {
    "hospedaria",
    "hotel de 3 estrelas",
    "hotel",
    "hotel de 5 estrelas",
    "hotel de 4 estrelas",
    "hotel resort",
    "hospedagem domiciliar",
    "hotel de 2 estrelas",
    "albergue"
}

# Output settings
OUTPUT_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hotel_portugal.csv")
PROGRESS_FILE = os.path.join(os.path.dirname(OUTPUT_CSV), "scraping_progress_hotel_pt.json")

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
