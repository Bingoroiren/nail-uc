import urllib.request
import csv
import io
import os
import math

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculates the approximate distance in kilometers between two lat/lng coordinates using Haversine formula."""
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

# Core major cities of Albania to guarantee presence
FALLBACK_ALBANIA_CITIES = [
    {"name": "Tirana", "state": "Tiranë", "lat": 41.3275, "lng": 19.8187, "population": 526000},
    {"name": "Durrës", "state": "Durrës", "lat": 41.3163, "lng": 19.4474, "population": 195000},
    {"name": "Vlorë", "state": "Vlorë", "lat": 40.4500, "lng": 19.4833, "population": 115000},
    {"name": "Shkodër", "state": "Shkodër", "lat": 42.0681, "lng": 19.5121, "population": 95000},
    {"name": "Elbasan", "state": "Elbasan", "lat": 41.1131, "lng": 20.0818, "population": 66000},
    {"name": "Fier", "state": "Fier", "lat": 40.7167, "lng": 19.5500, "population": 53000},
    {"name": "Korçë", "state": "Korçë", "lat": 40.6167, "lng": 20.7667, "population": 43000},
    {"name": "Berat", "state": "Berat", "lat": 40.7049, "lng": 19.9497, "population": 40000},
    {"name": "Lushnjë", "state": "Fier", "lat": 40.9333, "lng": 19.7000, "population": 22000},
    {"name": "Pogradec", "state": "Korçë", "lat": 40.9000, "lng": 20.6500, "population": 21000},
    {"name": "Kavajë", "state": "Tiranë", "lat": 41.1833, "lng": 19.5500, "population": 20000},
    {"name": "Gjirokastër", "state": "Gjirokastër", "lat": 40.0758, "lng": 20.1389, "population": 20000},
    {"name": "Sarandë", "state": "Vlorë", "lat": 39.8750, "lng": 20.0100, "population": 20000},
    {"name": "Lezhë", "state": "Lezhë", "lat": 41.7836, "lng": 19.6436, "population": 15000},
    {"name": "Kukës", "state": "Kukës", "lat": 42.0767, "lng": 20.4219, "population": 16000},
    {"name": "Peshkopi", "state": "Dibër", "lat": 41.6847, "lng": 20.4289, "population": 13000},
    {"name": "Krujë", "state": "Durrës", "lat": 41.5092, "lng": 19.7928, "population": 12000},
    {"name": "Patos", "state": "Fier", "lat": 40.6833, "lng": 19.6167, "population": 15000},
    {"name": "Kuçovë", "state": "Berat", "lat": 40.8000, "lng": 19.9167, "population": 12000}
]

def main():
    url = "https://simplemaps.com/static/data/country-cities/al/al.csv"
    print(f"[*] Downloading Albania locations database from: {url}")
    
    csv_data = None
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            csv_data = response.read().decode('utf-8')
    except Exception as e:
        print(f"[-] Download failed: {e}. Using fallback database.")
        
    raw_locations = []
    if csv_data:
        print("[*] Parsing CSV and filtering locations...")
        reader = csv.DictReader(io.StringIO(csv_data))
        
        for row in reader:
            locality = row.get("city", "").strip()
            state = row.get("admin_name", "").strip()
            lat_str = row.get("lat", "").strip()
            lng_str = row.get("lng", "").strip()
            pop_str = row.get("population", "0").strip()
            
            if not locality or not lat_str or not lng_str:
                continue
                
            try:
                lat = float(lat_str)
                lng = float(lng_str)
                pop = float(pop_str) if pop_str else 0
                
                # Albania bounding box coordinates: (39.5 < lat < 42.8) and (19.1 < lng < 21.2)
                if not (39.5 <= lat <= 42.8) or not (19.1 <= lng <= 21.2):
                    continue
                
                raw_locations.append({
                    "state": state if state else "Albania",
                    "name": locality,
                    "lat": lat,
                    "lng": lng,
                    "population": pop
                })
            except ValueError:
                continue
    else:
        raw_locations = FALLBACK_ALBANIA_CITIES

    # Sort descending by population so larger cities become cluster centers
    raw_locations.sort(key=lambda x: x.get("population", 0), reverse=True)
    print(f"[+] Loaded {len(raw_locations)} valid locations.")
    
    print("[*] Performing spatial clustering to eliminate overlaps (radius ~10.0 km)...")
    clustered_locations = []
    threshold_km = 10.0
    
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
                "lat": round(loc["lat"], 4),
                "lng": round(loc["lng"], 4),
                "zoom": 11,
                "covered_suburbs": [loc["name"]]
            })
            
    print(f"[+] Spatial clustering complete: Reduced from {len(raw_locations)} to {len(clustered_locations)} optimized coordinate points.")
    
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locations_al.py")
    print(f"[*] Writing {len(clustered_locations)} clustered locations to {output_path}...")
    
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("# Generated automatically by generate_locations_al.py\n")
            f.write("# Covers all populated locations and economic hubs in Albania using spatial clustering.\n\n")
            f.write("LOCATIONS = [\n")
            for loc in clustered_locations:
                f.write("    {\n")
                f.write(f'        "name": "{loc["name"]}",\n')
                f.write(f'        "state": "{loc["state"]}",\n')
                f.write(f'        "lat": {loc["lat"]},\n')
                f.write(f'        "lng": {loc["lng"]},\n')
                f.write(f'        "zoom": {loc["zoom"]},\n')
                f.write(f'        "covered_suburbs": {loc["covered_suburbs"]}\n')
                f.write("    },\n")
            f.write("]\n")
        print(f"[SUCCESS] Successfully generated {output_path} with {len(clustered_locations)} target points.")
    except Exception as e:
        print(f"[-] Failed to write locations file: {e}")

if __name__ == "__main__":
    main()
