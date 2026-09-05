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
    """Calculates approximate distance in kilometers between two lat/lng coordinates."""
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

# Curated key agricultural, dairy & aquaculture hubs across Finland
FALLBACK_FINLAND_LOCATIONS = [
    # Varsinais-Suomi (Southwest Finland - Finland's main crop & vegetable agricultural belt)
    {"state": "Varsinais-Suomi", "name": "Turku", "lat": 60.4518, "lng": 22.2666},
    {"state": "Varsinais-Suomi", "name": "Salo", "lat": 60.3833, "lng": 23.1333},
    {"state": "Varsinais-Suomi", "name": "Loimaa", "lat": 60.8500, "lng": 23.0500},
    {"state": "Varsinais-Suomi", "name": "Uusikaupunki", "lat": 60.8000, "lng": 21.4167},
    {"state": "Varsinais-Suomi", "name": "Paimio", "lat": 60.4567, "lng": 22.6867},

    # Etelä-Pohjanmaa & Pohjanmaa (Finland's farming heartland - livestock, dairy & crops)
    {"state": "Etelä-Pohjanmaa", "name": "Seinäjoki", "lat": 62.7903, "lng": 22.8403},
    {"state": "Etelä-Pohjanmaa", "name": "Lapua", "lat": 62.9667, "lng": 23.0000},
    {"state": "Etelä-Pohjanmaa", "name": "Kauhajoki", "lat": 62.4333, "lng": 22.1833},
    {"state": "Etelä-Pohjanmaa", "name": "Kurikka", "lat": 62.6167, "lng": 22.4000},
    {"state": "Etelä-Pohjanmaa", "name": "Alavus", "lat": 62.5833, "lng": 23.6167},
    {"state": "Pohjanmaa", "name": "Vaasa", "lat": 63.0960, "lng": 21.6158},
    {"state": "Pohjanmaa", "name": "Pedersöre", "lat": 63.6000, "lng": 22.6833},
    {"state": "Keski-Pohjanmaa", "name": "Kokkola", "lat": 63.8385, "lng": 23.1307},

    # Uusimaa
    {"state": "Uusimaa", "name": "Helsinki", "lat": 60.1699, "lng": 24.9384},
    {"state": "Uusimaa", "name": "Porvoo", "lat": 60.3931, "lng": 25.6639},
    {"state": "Uusimaa", "name": "Lohja", "lat": 60.2500, "lng": 24.0667},
    {"state": "Uusimaa", "name": "Raasepori", "lat": 59.9750, "lng": 23.4333},
    {"state": "Uusimaa", "name": "Hyvinkää", "lat": 60.6333, "lng": 24.8667},
    {"state": "Uusimaa", "name": "Mäntsälä", "lat": 60.6333, "lng": 25.3167},

    # Satakunta
    {"state": "Satakunta", "name": "Pori", "lat": 61.4851, "lng": 21.7974},
    {"state": "Satakunta", "name": "Rauma", "lat": 61.1272, "lng": 21.5117},
    {"state": "Satakunta", "name": "Huittinen", "lat": 61.1833, "lng": 22.7000},
    {"state": "Satakunta", "name": "Kankaanpää", "lat": 61.8000, "lng": 22.4000},

    # Pirkanmaa & Häme
    {"state": "Pirkanmaa", "name": "Tampere", "lat": 61.4978, "lng": 23.7610},
    {"state": "Pirkanmaa", "name": "Sastamala", "lat": 61.3417, "lng": 22.9083},
    {"state": "Pirkanmaa", "name": "Orivesi", "lat": 61.6783, "lng": 24.3583},
    {"state": "Kanta-Häme", "name": "Hämeenlinna", "lat": 60.9958, "lng": 24.4642},
    {"state": "Kanta-Häme", "name": "Forssa", "lat": 60.8142, "lng": 23.6214},
    {"state": "Päijät-Häme", "name": "Lahti", "lat": 60.9827, "lng": 25.6615},
    {"state": "Päijät-Häme", "name": "Heinola", "lat": 61.2056, "lng": 26.0381},

    # Savo & Karjala (Dairy & fish farming hubs)
    {"state": "Etelä-Savo", "name": "Mikkeli", "lat": 61.6886, "lng": 27.2723},
    {"state": "Etelä-Savo", "name": "Savonlinna", "lat": 61.8681, "lng": 28.8800},
    {"state": "Etelä-Savo", "name": "Pieksämäki", "lat": 62.3000, "lng": 27.1333},
    {"state": "Pohjois-Savo", "name": "Kuopio", "lat": 62.8924, "lng": 27.6770},
    {"state": "Pohjois-Savo", "name": "Iisalmi", "lat": 63.5611, "lng": 27.1903},
    {"state": "Pohjois-Savo", "name": "Kiuruvesi", "lat": 63.6500, "lng": 26.6167},
    {"state": "Pohjois-Karjala", "name": "Joensuu", "lat": 62.6010, "lng": 29.7636},
    {"state": "Pohjois-Karjala", "name": "Lieksa", "lat": 63.3167, "lng": 30.0167},

    # Keski-Suomi
    {"state": "Keski-Suomi", "name": "Jyväskylä", "lat": 62.2426, "lng": 25.7473},
    {"state": "Keski-Suomi", "name": "Äänekoski", "lat": 62.6000, "lng": 25.7167},
    {"state": "Keski-Suomi", "name": "Jämsä", "lat": 61.8642, "lng": 25.1900},

    # Pohjois-Pohjanmaa & Kainuu & Lappi
    {"state": "Pohjois-Pohjanmaa", "name": "Oulu", "lat": 65.0121, "lng": 25.4651},
    {"state": "Pohjois-Pohjanmaa", "name": "Ylivieska", "lat": 64.0722, "lng": 24.5361},
    {"state": "Pohjois-Pohjanmaa", "name": "Raahe", "lat": 64.6833, "lng": 24.4833},
    {"state": "Pohjois-Pohjanmaa", "name": "Kuusamo", "lat": 65.9667, "lng": 29.1833},
    {"state": "Kainuu", "name": "Kajaani", "lat": 64.2250, "lng": 27.7278},
    {"state": "Lappi", "name": "Rovaniemi", "lat": 66.5000, "lng": 25.7167},
    {"state": "Lappi", "name": "Kemi", "lat": 65.7333, "lng": 24.5667},
    {"state": "Lappi", "name": "Tornio", "lat": 65.8481, "lng": 24.1467}
]

def main():
    url = "https://simplemaps.com/static/data/country-cities/fi/fi.csv"
    print(f"[*] Downloading Finland locations database from: {url}")
    
    raw_locations = list(FALLBACK_FINLAND_LOCATIONS)
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
                        if 59.8 < lat < 70.1 and 19.5 < lng < 31.6:
                            raw_locations.append({
                                "state": state if state else "Finland",
                                "name": locality,
                                "lat": lat,
                                "lng": lng
                            })
                    except ValueError:
                        pass
        print(f"[+] Combined with online cities dataset. Total raw locations: {len(raw_locations)}")
    except Exception as e:
        print(f"[-] Online download failed ({e}). Using curated fallback Finland locations dataset.")

    print("[*] Performing spatial clustering (radius ~20.0 km, zoom=11)...")
    clustered_locations = []
    threshold_km = 20.0
    
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
    
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locations_fi.py")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Generated automatically for Finland Farms & Aquaculture Scraper\n")
        f.write("# Covers all Finland regions with spatial clustering (zoom level 11)\n\n")
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
