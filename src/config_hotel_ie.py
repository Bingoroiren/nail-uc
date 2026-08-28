import os

# Google Maps Search Keywords for Ireland Hotels & Hospitality
KEYWORDS = [
    "5-star hotel",
    "4-star hotel",
    "3-star hotel",
    "2-star hotel",
    "Hostel",
    "Homestay",
    "Guest house",
    "Holiday home",
    "Vacation Rental",
    "Hotel",
    "Resort"
]

# Allowed Category Tags for strict filtering (lowercase)
ALLOWED_CATEGORIES = {
    "5-star hotel",
    "4-star hotel",
    "3-star hotel",
    "2-star hotel",
    "1-star hotel",
    "hostel",
    "homestay",
    "guest house",
    "guesthouse",
    "holiday home",
    "vacation rental",
    "hotel",
    "resort",
    "resort hotel",
    "bed & breakfast",
    "b&b",
    "extended stay hotel",
    "serviced accommodation",
    "lodging",
    "inn"
}

# Output file settings
OUTPUT_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw", "hotel_ireland.csv")
PROGRESS_FILE = os.path.join(os.path.dirname(os.path.dirname(OUTPUT_CSV)), "progress", "scraping_progress_hotel_ie.json")

# Playwright Browser Settings
HEADLESS = False   # Set to True for headless running
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
