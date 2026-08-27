# config_kr.py
# Settings and Naver Map selectors for the South Korea recruitment agency scraper

import os

# Output File Paths
OUTPUT_CSV = r"d:\glc\nail uc\korean_agencies.csv"
OUTPUT_XLSX = r"d:\glc\nail uc\korean_agencies.xlsx"

# Search settings
KEYWORDS = [
    "파견,헤드헌팅",
    "직업안내",
    "인력공급,고용알선",
    "외국인근로자센터"
]

# Category tags to filter and save
TARGET_TAGS = [
    "파견,헤드헌팅",
    "직업안내",
    "인력공급,고용알선",
    "외국인근로자센터"
]

# CSS Selectors for Naver Map elements
# Note: Naver Map has dynamic/minified CSS class names, so we combine standard class selectors
# with structural/tag selectors for maximum stability and robustness.
SELECTORS = {
    # Main search input on Naver Map landing page (if navigating from homepage)
    "search_input": "input.input_search",
    
    # Search Results frame selectors (context is page.frame_locator("#searchIframe"))
    "results_container": "#_pcmap_list_scroll_container",
    "result_item": "li", 
    "result_title_link": "a[href*='place.naver.com'] span, li a span, .place_item_name",
    "next_page_btn": "a[title='다음페이지'], a:has-text('다음'), a:has-text('>')",
    
    # Details panel frame selectors (context is page.frame_locator("#entryIframe"))
    "business_name": "span.Fc1nC, .place_title, h1, #_title span",
    "category": "span.DJJsn, .place_category, span.place_category",
    "address": "span.LDgSu, .address, span.address",
    "phone": "span.xlx7Q, .phone, span.phone",
    "website": "a.Pv9Cm, a[href*='http']:has-text('홈페이지'), a.ChSharedPlaceWebsite"
}
