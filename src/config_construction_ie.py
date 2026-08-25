import os

# Google Maps Search Keywords for Ireland Construction Contractors & Manufacturing Factories
# (Excluding Corporate office from search keywords as directed)
KEYWORDS = [
    "Carport and pergola builder",
    "Construction company",
    "Home builder",
    "Custom home builder",
    "Modular home builder",
    "General contractor",
    "Shed builder",
    "Building restoration service",
    "Bricklayer",
    "Roofing contractor",
    "Paving contractor",
    "Manufacturer",
    "Medical equipment manufacturer",
    "Semi conductor supplier",
    "Electronics manufacturer"
]

# Allowed Category Tags for strict filtering (lowercase)
# (Includes Corporate office for filtering)
ALLOWED_CATEGORIES = {
    "carport and pergola builder",
    "construction company",
    "home builder",
    "custom home builder",
    "modular home builder",
    "general contractor",
    "shed builder",
    "building restoration service",
    "bricklayer",
    "roofing contractor",
    "paving contractor",
    "manufacturer",
    "medical equipment manufacturer",
    "semi conductor supplier",
    "semiconductor supplier",
    "electronics manufacturer",
    "corporate office",
    "building contractor",
    "civil engineering company",
    "factory",
    "industrial equipment supplier",
    "electronics factory"
}

# Output file settings
OUTPUT_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "construction_ireland.csv")
PROGRESS_FILE = os.path.join(os.path.dirname(OUTPUT_CSV), "scraping_progress_construction_ie.json")

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
