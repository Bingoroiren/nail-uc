# -*- coding: utf-8 -*-
"""
CONFIG GOOGLE MAPS SCRAPER - LITHUANIAN METAL & FABRICATION FACTORIES (LT_METL_GMAP)
=====================================================================================
Target: Lithuanian Fabricated Metal, Metalworking, Machining, Welding, Foundries & Steel Structures
Output: LT_METL_GMAP_0RAW.csv
"""

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

# Output Settings (Rule 10: Fixed 17-char filename LT_METL_GMAP_0RAW.csv)
OUTPUT_CSV = str(ROOT_DIR / "LT_METL_GMAP_0RAW.csv")
RAW_DATA_CSV = str(ROOT_DIR / "data" / "raw" / "LT_METL_GMAP_0RAW.csv")
PROGRESS_FILE = str(ROOT_DIR / "progress" / "progress_metal_lt.json")

# Google Maps Search Keywords (Lithuanian native terminology for metal factories)
KEYWORDS = [
    "Metalo apdirbimas",               # Metal processing / Metalworking
    "Metalo gaminiai",                 # Metal products / Fabricated metal
    "Metalo konstrukcijos",            # Metal structures / Steel structures
    "Metalo apdirbimo įmonė",          # Metal processing company
    "Metalo gamykla",                  # Metal factory / plant
    "Mechaninis apdirbimas",           # Machining / CNC mechanical processing
    "Liejykla",                        # Foundry / Metal casting
    "Suvirinimo darbai",               # Welding works
    "Metalo pjaustymas lazeriu",       # Laser cutting metal / Sheet metal
    "Štampavimas",                     # Metal stamping / pressing
]

# Google Maps Allowed Categories Filter (Both Lithuanian and English)
ALLOWED_CATEGORIES = [
    # Lithuanian Categories
    "Metalo apdirbimas",
    "Metalo apdirbimo įmonė",
    "Metalo dirbinių gamintojas",
    "Metalo konstrukcijų gamintojas",
    "Plieno gamintojas",
    "Suvirintojas",
    "Suvirinimo paslaugos",
    "Liejykla",
    "Mechaninis apdirbimas",
    "Gamykla",
    "Gamintojas",
    "Pramonės įmonė",
    "Pramonės įranga",
    "Mašinų gamykla",
    "Lazerinis pjovimas",
    "Štampavimas",
    "Kalvystė",
    
    # English Categories
    "Metal fabricator",
    "Metal supplier",
    "Metal processing company",
    "Steel fabricator",
    "Sheet metal contractor",
    "Machining manufacturer",
    "Foundry",
    "Welder",
    "Manufacturer",
    "Factory",
    "Mechanical engineer",
    "Industrial equipment supplier",
    "Laser cutting service",
    "Blacksmith",
]

# Playwright Browser Settings (Rule 4: headless=False, viewport >= 1280x800)
HEADLESS = False
SLOW_MO = 5
TIMEOUT = 60000  # 60s timeout

# Delay Settings (Seconds)
MIN_DELAY = 0.2
MAX_DELAY = 0.5

# Google Maps Selectors
SELECTORS = {
    # Left pane containing search results (scrollable list container)
    "results_container": 'div[role="feed"]',
    
    # Anchor tag for each business listing in the search results
    "listing_link": 'a.hfpxzc',
    
    # Detail panel elements
    "business_name": 'h1.DUwDvf',
    "website": 'a[data-item-id="authority"]',
    "phone": 'button[data-item-id^="phone:tel:"]',
    "address": 'button[data-item-id^="address"]',
    
    # Extra information (Rating, Reviews, Category)
    "rating": 'div.F7nice span[aria-hidden="true"]',
    "reviews_count": 'div.F7nice span[aria-label*="reviews"], div.F7nice span[aria-label*="atsiliep"]',
    "category": 'button.DkEaCc, button.DkEaL, button[jsaction*="category"], [jsaction*="category"]',
}

