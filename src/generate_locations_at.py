import urllib.request
import csv
import io
import os
import math
import sys
import codecs

if sys.platform.startswith('win') and hasattr(sys.stdout, 'buffer'):
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculates the approximate distance in kilometers between two lat/lng coordinates."""
    R = 6371.0
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad
    
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# Fallback curated key agricultural hubs across all 9 Bundesländer of Austria
FALLBACK_AUSTRIA_LOCATIONS = [
    # Niederösterreich (Lower Austria)
    {"state": "Niederösterreich", "name": "St. Pölten", "lat": 48.2047, "lng": 15.6256},
    {"state": "Niederösterreich", "name": "Wiener Neustadt", "lat": 47.8131, "lng": 16.2444},
    {"state": "Niederösterreich", "name": "Krems an der Donau", "lat": 48.4092, "lng": 15.6142},
    {"state": "Niederösterreich", "name": "Baden", "lat": 48.0069, "lng": 16.2308},
    {"state": "Niederösterreich", "name": "Mistelbach", "lat": 48.5670, "lng": 16.5744},
    {"state": "Niederösterreich", "name": "Amstetten", "lat": 48.1228, "lng": 14.8722},
    {"state": "Niederösterreich", "name": "Zwettl", "lat": 48.6042, "lng": 15.1689},
    {"state": "Niederösterreich", "name": "Horn", "lat": 48.6625, "lng": 15.6569},
    {"state": "Niederösterreich", "name": "Hollabrunn", "lat": 48.5625, "lng": 16.0828},
    {"state": "Niederösterreich", "name": "Melk", "lat": 48.2269, "lng": 15.3314},
    {"state": "Niederösterreich", "name": "Gänserndorf", "lat": 48.3411, "lng": 16.7194},
    {"state": "Niederösterreich", "name": "Waidhofen an der Ybbs", "lat": 47.9600, "lng": 14.7739},

    # Oberösterreich (Upper Austria)
    {"state": "Oberösterreich", "name": "Linz", "lat": 48.3069, "lng": 14.2858},
    {"state": "Oberösterreich", "name": "Wels", "lat": 48.1564, "lng": 14.0247},
    {"state": "Oberösterreich", "name": "Steyr", "lat": 48.0428, "lng": 14.4214},
    {"state": "Oberösterreich", "name": "Vöcklabruck", "lat": 48.0089, "lng": 13.6558},
    {"state": "Oberösterreich", "name": "Braunau am Inn", "lat": 48.2567, "lng": 13.0353},
    {"state": "Oberösterreich", "name": "Ried im Innkreis", "lat": 48.2103, "lng": 13.4889},
    {"state": "Oberösterreich", "name": "Freistadt", "lat": 48.5117, "lng": 14.5050},
    {"state": "Oberösterreich", "name": "Gmunden", "lat": 47.9186, "lng": 13.7994},
    {"state": "Oberösterreich", "name": "Schärding", "lat": 48.4578, "lng": 13.4319},
    {"state": "Oberösterreich", "name": "Rohrbach-Berg", "lat": 48.5728, "lng": 13.9917},

    # Steiermark (Styria)
    {"state": "Steiermark", "name": "Graz", "lat": 47.0707, "lng": 15.4395},
    {"state": "Steiermark", "name": "Leoben", "lat": 47.3800, "lng": 15.0983},
    {"state": "Steiermark", "name": "Feldbach", "lat": 46.9536, "lng": 15.8886},
    {"state": "Steiermark", "name": "Deutschlandsberg", "lat": 46.8142, "lng": 15.2144},
    {"state": "Steiermark", "name": "Leibnitz", "lat": 46.7817, "lng": 15.5375},
    {"state": "Steiermark", "name": "Weiz", "lat": 47.2181, "lng": 15.6247},
    {"state": "Steiermark", "name": "Hartberg", "lat": 47.2817, "lng": 15.9694},
    {"state": "Steiermark", "name": "Liezen", "lat": 47.5686, "lng": 14.2417},
    {"state": "Steiermark", "name": "Kapfenberg", "lat": 47.4439, "lng": 15.3122},

    # Tirol (Tyrol)
    {"state": "Tirol", "name": "Innsbruck", "lat": 47.2692, "lng": 11.4041},
    {"state": "Tirol", "name": "Kufstein", "lat": 47.5833, "lng": 12.1667},
    {"state": "Tirol", "name": "Schwaz", "lat": 47.3481, "lng": 11.7083},
    {"state": "Tirol", "name": "Telfs", "lat": 47.3069, "lng": 11.0736},
    {"state": "Tirol", "name": "Imst", "lat": 47.2394, "lng": 10.7417},
    {"state": "Tirol", "name": "Lienz", "lat": 46.8297, "lng": 12.7686},
    {"state": "Tirol", "name": "Kitzbühel", "lat": 47.4464, "lng": 12.3922},

    # Kärnten (Carinthia)
    {"state": "Kärnten", "name": "Klagenfurt", "lat": 46.6247, "lng": 14.3053},
    {"state": "Kärnten", "name": "Villach", "lat": 46.6111, "lng": 13.8558},
    {"state": "Kärnten", "name": "St. Veit an der Glan", "lat": 46.7667, "lng": 14.3667},
    {"state": "Kärnten", "name": "Spittal an der Drau", "lat": 46.7917, "lng": 13.4958},
    {"state": "Kärnten", "name": "Wolfsberg", "lat": 46.8378, "lng": 14.8425},
    {"state": "Kärnten", "name": "Völkermarkt", "lat": 46.6622, "lng": 14.6344},

    # Salzburg
    {"state": "Salzburg", "name": "Salzburg", "lat": 47.8095, "lng": 13.0550},
    {"state": "Salzburg", "name": "Hallein", "lat": 47.6833, "lng": 13.1000},
    {"state": "Salzburg", "name": "Saalfelden", "lat": 47.4267, "lng": 12.8489},
    {"state": "Salzburg", "name": "St. Johann im Pongau", "lat": 47.3500, "lng": 13.2000},
    {"state": "Salzburg", "name": "Zell am See", "lat": 47.3250, "lng": 12.7967},
    {"state": "Salzburg", "name": "Tamsweg", "lat": 47.1283, "lng": 13.8114},

    # Vorarlberg
    {"state": "Vorarlberg", "name": "Dornbirn", "lat": 47.4125, "lng": 9.7417},
    {"state": "Vorarlberg", "name": "Feldkirch", "lat": 47.2378, "lng": 9.5983},
    {"state": "Vorarlberg", "name": "Bregenz", "lat": 47.5031, "lng": 9.7472},
    {"state": "Vorarlberg", "name": "Bludenz", "lat": 47.1558, "lng": 9.8208},
    {"state": "Vorarlberg", "name": "Bezau", "lat": 47.3842, "lng": 9.8972},

    # Burgenland
    {"state": "Burgenland", "name": "Eisenstadt", "lat": 47.8456, "lng": 16.5236},
    {"state": "Burgenland", "name": "Neusiedl am See", "lat": 47.9489, "lng": 16.8436},
    {"state": "Burgenland", "name": "Oberwart", "lat": 47.2878, "lng": 16.2039},
    {"state": "Burgenland", "name": "Mattersburg", "lat": 47.7389, "lng": 16.3986},
    {"state": "Burgenland", "name": "Güssing", "lat": 47.0597, "lng": 16.3242},

    # Wien (Vienna)
    {"state": "Wien", "name": "Wien", "lat": 48.2082, "lng": 16.3738}
]

def main():
    url = "https://simplemaps.com/static/data/country-cities/at/at.csv"
    print(f"[*] Downloading Austria locations database from: {url}")
    
    raw_locations = []
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            csv_data = response.read().decode('utf-8')
            reader = csv.DictReader(io.StringIO(csv_data))
            for row in reader:
                locality = row.get("city", "").strip()
                state = row.get("admin_name", "").strip()
                lat_str = row.get("lat", "").strip()
                lng_str = row.get("lng", "").strip()
                if locality and lat_str and lng_str:
                    try:
                        lat = float(lat_str)
                        lng = float(lng_str)
                        if 46.3 < lat < 49.1 and 9.5 < lng < 17.2:
                            raw_locations.append({
                                "state": state if state else "Austria",
                                "name": locality,
                                "lat": lat,
                                "lng": lng
                            })
                    except ValueError:
                        pass
        print(f"[+] Downloaded {len(raw_locations)} cities from SimpleMaps.")
    except Exception as e:
        print(f"[-] Online download failed ({e}). Using curated fallback Austria locations dataset.")
        raw_locations = FALLBACK_AUSTRIA_LOCATIONS

    if not raw_locations:
        raw_locations = FALLBACK_AUSTRIA_LOCATIONS

    print("[*] Performing spatial clustering (radius ~15.0 km, zoom=11)...")
    clustered_locations = []
    threshold_km = 15.0
    
    for loc in raw_locations:
        is_covered = False
        for center in clustered_locations:
            dist = calculate_distance(loc["lat"], loc["lng"], center["lat"], center["lng"])
            if dist <= threshold_km:
                is_covered = True
                if loc["name"] not in center["covered_suburbs"]:
                    center["covered_suburbs"].append(loc["name"])
                break
                
        if not is_covered:
            clustered_locations.append({
                "state": loc["state"],
                "name": loc["name"],
                "lat": loc["lat"],
                "lng": loc["lng"],
                "zoom": 11,
                "covered_suburbs": [loc["name"]]
            })
            
    print(f"[+] Spatial clustering complete: {len(clustered_locations)} optimized coordinate centers.")
    
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locations_at.py")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Generated automatically for Austria Farms & Agriculture Scraper\n")
        f.write("# Covers all 9 Bundesländer of Austria with spatial clustering (zoom level 11)\n\n")
        f.write("LOCATIONS = [\n")
        for loc in clustered_locations:
            suburbs_str = ", ".join(loc["covered_suburbs"][:5])
            if len(loc["covered_suburbs"]) > 5:
                suburbs_str += f" and {len(loc['covered_suburbs']) - 5} more"
            f.write(f'    # Covers: {suburbs_str}\n')
            f.write(f'    {{"state": "{loc["state"]}", "name": "{loc["name"]}", "lat": {loc["lat"]:.6f}, "lng": {loc["lng"]:.6f}, "zoom": {loc["zoom"]}}},\n')
        f.write("]\n")
        
    print(f"[SUCCESS] Locations written to {output_path}")

if __name__ == "__main__":
    main()
