# -*- coding: utf-8 -*-
"""
CONFIG GOOGLE MAPS SCRAPER - FRANCE RECRUITMENT & INTERIM AGENCIES (FR_AGCY_GMAP)
===================================================================================
Target: Paris & Île-de-France International Recruitment, Executive Search & Temp/Interim Agencies
Output: FR_AGCY_GMAP_0RAW.csv (Rule 10: Fixed 17-char name)
"""

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

# Output Settings (Rule 10: Fixed 17-char filename FR_AGCY_GMAP_0RAW.csv)
OUTPUT_CSV = str(ROOT_DIR / "FR_AGCY_GMAP_0RAW.csv")
RAW_DATA_CSV = str(ROOT_DIR / "data" / "raw" / "FR_AGCY_GMAP_0RAW.csv")
PROGRESS_FILE = str(ROOT_DIR / "progress" / "progress_agcy_fr.json")

# Google Maps Search Keywords (Trực tiếp từ 2 danh mục yêu cầu: Recrutement international & Agences d'intérim)
KEYWORDS = [
    "Recrutement international",
    "Cabinet de recrutement international",
    "Agence d'intérim",
    "Agence de travail temporaire",
    "Société de travail temporaire",
    "Cabinet de recrutement",
    "Agence de placement",
    "Recrutement cadres",
    "Interim BTP",
    "Interim logistique"
]

# Google Maps Allowed Categories Filter (Chỉ nhận diện đúng các ngành Tuyển dụng / Interim)
ALLOWED_CATEGORIES = [
    "Agence d'intérim",
    "Cabinet de recrutement",
    "Agence de travail temporaire",
    "Service de recherche d'emploi",
    "Conseiller en recherche d'emploi",
    "Agence pour l'emploi",
    "Bureau de placement",
    "Société de conseil en ressources humaines",
    "Consultant en ressources humaines",
    "Employment agency",
    "Recruiter",
    "Temp agency",
    "Human resource consulting",
    "Executive search firm",
    "Staffing agency"
]

# Permanent Blacklist
PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre'
]

