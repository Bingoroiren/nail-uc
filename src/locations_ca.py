# Generated manually - covers major populated areas in Canada using spatial clustering.
# Zoom 11 for large cities, zoom 10 for smaller cities/wide rural coverage.

LOCATIONS = [
    # Ontario
    {"state": "Ontario", "name": "Toronto", "lat": 43.6532, "lng": -79.3832, "zoom": 11},
    {"state": "Ontario", "name": "Ottawa", "lat": 45.4215, "lng": -75.6972, "zoom": 11},
    {"state": "Ontario", "name": "Mississauga", "lat": 43.5890, "lng": -79.6441, "zoom": 11},
    {"state": "Ontario", "name": "Brampton", "lat": 43.7315, "lng": -79.7624, "zoom": 11},
    {"state": "Ontario", "name": "Hamilton", "lat": 43.2557, "lng": -79.8711, "zoom": 11},
    {"state": "Ontario", "name": "London", "lat": 42.9849, "lng": -81.2453, "zoom": 11},
    {"state": "Ontario", "name": "Markham", "lat": 43.8561, "lng": -79.3370, "zoom": 11},
    {"state": "Ontario", "name": "Kitchener", "lat": 43.4516, "lng": -80.4925, "zoom": 11},
    {"state": "Ontario", "name": "Windsor", "lat": 42.3149, "lng": -83.0364, "zoom": 11},
    {"state": "Ontario", "name": "Oakville", "lat": 43.4675, "lng": -79.6877, "zoom": 11},
    {"state": "Ontario", "name": "Barrie", "lat": 44.3894, "lng": -79.6903, "zoom": 11},
    {"state": "Ontario", "name": "Vaughan", "lat": 43.8361, "lng": -79.4982, "zoom": 11},
    {"state": "Ontario", "name": "Oshawa", "lat": 43.8971, "lng": -78.8658, "zoom": 11},
    {"state": "Ontario", "name": "Kingston", "lat": 44.2312, "lng": -76.4860, "zoom": 11},
    {"state": "Ontario", "name": "Sudbury", "lat": 46.4917, "lng": -80.9930, "zoom": 10},
    {"state": "Ontario", "name": "Thunder Bay", "lat": 48.3809, "lng": -89.2477, "zoom": 10},
    {"state": "Ontario", "name": "Guelph", "lat": 43.5448, "lng": -80.2482, "zoom": 11},
    {"state": "Ontario", "name": "Cambridge", "lat": 43.3616, "lng": -80.3144, "zoom": 11},
    {"state": "Ontario", "name": "St. Catharines", "lat": 43.1594, "lng": -79.2469, "zoom": 11},

    # British Columbia
    {"state": "British Columbia", "name": "Vancouver", "lat": 49.2827, "lng": -123.1207, "zoom": 11},
    {"state": "British Columbia", "name": "Surrey", "lat": 49.1913, "lng": -122.8490, "zoom": 11},
    {"state": "British Columbia", "name": "Burnaby", "lat": 49.2488, "lng": -122.9805, "zoom": 11},
    {"state": "British Columbia", "name": "Richmond", "lat": 49.1666, "lng": -123.1336, "zoom": 11},
    {"state": "British Columbia", "name": "Kelowna", "lat": 49.8880, "lng": -119.4960, "zoom": 11},
    {"state": "British Columbia", "name": "Abbotsford", "lat": 49.0504, "lng": -122.3045, "zoom": 11},
    {"state": "British Columbia", "name": "Victoria", "lat": 48.4284, "lng": -123.3656, "zoom": 11},
    {"state": "British Columbia", "name": "Coquitlam", "lat": 49.2838, "lng": -122.7932, "zoom": 11},
    {"state": "British Columbia", "name": "Prince George", "lat": 53.9171, "lng": -122.7497, "zoom": 10},
    {"state": "British Columbia", "name": "Kamloops", "lat": 50.6745, "lng": -120.3273, "zoom": 10},
    {"state": "British Columbia", "name": "Langley", "lat": 49.1044, "lng": -122.6604, "zoom": 11},
    {"state": "British Columbia", "name": "Nanaimo", "lat": 49.1659, "lng": -123.9401, "zoom": 11},

    # Quebec
    {"state": "Quebec", "name": "Montreal", "lat": 45.5017, "lng": -73.5673, "zoom": 11},
    {"state": "Quebec", "name": "Quebec City", "lat": 46.8139, "lng": -71.2080, "zoom": 11},
    {"state": "Quebec", "name": "Laval", "lat": 45.5663, "lng": -73.6921, "zoom": 11},
    {"state": "Quebec", "name": "Longueuil", "lat": 45.5315, "lng": -73.5169, "zoom": 11},
    {"state": "Quebec", "name": "Sherbrooke", "lat": 45.4042, "lng": -71.8929, "zoom": 11},
    {"state": "Quebec", "name": "Saguenay", "lat": 48.4002, "lng": -71.0569, "zoom": 10},
    {"state": "Quebec", "name": "Trois-Rivieres", "lat": 46.3432, "lng": -72.5418, "zoom": 11},
    {"state": "Quebec", "name": "Gatineau", "lat": 45.4765, "lng": -75.7013, "zoom": 11},

    # Alberta
    {"state": "Alberta", "name": "Calgary", "lat": 51.0447, "lng": -114.0719, "zoom": 11},
    {"state": "Alberta", "name": "Edmonton", "lat": 53.5461, "lng": -113.4938, "zoom": 11},
    {"state": "Alberta", "name": "Red Deer", "lat": 52.2690, "lng": -113.8116, "zoom": 11},
    {"state": "Alberta", "name": "Lethbridge", "lat": 49.6956, "lng": -112.8451, "zoom": 11},
    {"state": "Alberta", "name": "Airdrie", "lat": 51.2917, "lng": -114.0142, "zoom": 11},
    {"state": "Alberta", "name": "Medicine Hat", "lat": 50.0418, "lng": -110.6775, "zoom": 10},
    {"state": "Alberta", "name": "Grande Prairie", "lat": 55.1708, "lng": -118.7947, "zoom": 10},

    # Manitoba
    {"state": "Manitoba", "name": "Winnipeg", "lat": 49.8951, "lng": -97.1384, "zoom": 11},
    {"state": "Manitoba", "name": "Brandon", "lat": 49.8485, "lng": -99.9500, "zoom": 10},

    # Saskatchewan
    {"state": "Saskatchewan", "name": "Saskatoon", "lat": 52.1332, "lng": -106.6700, "zoom": 11},
    {"state": "Saskatchewan", "name": "Regina", "lat": 50.4452, "lng": -104.6189, "zoom": 11},
    {"state": "Saskatchewan", "name": "Prince Albert", "lat": 53.2033, "lng": -105.7532, "zoom": 10},

    # Nova Scotia
    {"state": "Nova Scotia", "name": "Halifax", "lat": 44.6488, "lng": -63.5752, "zoom": 11},
    {"state": "Nova Scotia", "name": "Cape Breton", "lat": 46.1368, "lng": -60.1942, "zoom": 10},

    # New Brunswick
    {"state": "New Brunswick", "name": "Moncton", "lat": 46.0878, "lng": -64.7782, "zoom": 11},
    {"state": "New Brunswick", "name": "Fredericton", "lat": 45.9636, "lng": -66.6431, "zoom": 11},
    {"state": "New Brunswick", "name": "Saint John", "lat": 45.2733, "lng": -66.0633, "zoom": 11},

    # Newfoundland
    {"state": "Newfoundland", "name": "St. John's", "lat": 47.5605, "lng": -52.7126, "zoom": 11},

    # Prince Edward Island
    {"state": "PEI", "name": "Charlottetown", "lat": 46.2382, "lng": -63.1311, "zoom": 11},
]

def get_locations():
    return LOCATIONS
