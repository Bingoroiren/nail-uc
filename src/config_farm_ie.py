import os

# Google Maps Search Keywords for Ireland Farms & Agriculture
# (Excluding Corporate office and Manufacturer from search keywords as directed)
KEYWORDS = [
    "Farm",
    "Dairy farm",
    "Honey farm",
    "Fruit and vegetable wholesaler",
    "Organic farm",
    "Orchard",
    "Dairy supplier",
    "Fruit and vegetable processing",
    "Mushroom Farm",
    "Greenhouse"
]

# Allowed Category Tags for strict filtering (lowercase)
# (Includes Corporate office and Manufacturer for filtering)
ALLOWED_CATEGORIES = {
    "farm",
    "dairy farm",
    "honey farm",
    "fruit and vegetable wholesaler",
    "organic farm",
    "orchard",
    "dairy supplier",
    "fruit and vegetable processing",
    "corporate office",
    "manufacturer",
    "mushroom farm",
    "greenhouse",
    "agricultural producer",
    "farm produce market",
    "produce wholesaler",
    "cattle farm",
    "poultry farm",
    "vegetable wholesaler",
    "fruit wholesaler"
}

# Output file settings
OUTPUT_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw", "farm_ireland.csv")
PROGRESS_FILE = os.path.join(os.path.dirname(os.path.dirname(OUTPUT_CSV)), "progress", "scraping_progress_farm_ie.json")

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
