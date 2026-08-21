import urllib.request
import csv
import io
import os
import math

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

def main():
    url = "https://simplemaps.com/static/data/country-cities/sk/sk.csv"
    print(f"[*] Downloading Slovakia locations database from: {url}")
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            csv_data = response.read().decode('utf-8')
    except Exception as e:
        print(f"[-] Download failed: {e}")
        return
        
    print("[*] Parsing CSV and filtering locations...")
    reader = csv.DictReader(io.StringIO(csv_data))
    
    raw_locations = []
    for row in reader:
        locality = row.get("city", "").strip()
        state = row.get("admin_name", "").strip()
        lat_str = row.get("lat", "").strip()
        lng_str = row.get("lng", "").strip()
        
        if not locality or not lat_str or not lng_str:
            continue
            
        try:
            lat = float(lat_str)
            lng = float(lng_str)
            # Slovakia bounding box coordinates check
            if not (47.5 < lat < 50.0) or not (16.5 < lng < 23.0):
                continue
            
            raw_locations.append({
                "state": state if state else "Slovakia",
                "name": locality,
                "lat": lat,
                "lng": lng
            })
        except ValueError:
            continue

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
                "lat": loc["lat"],
                "lng": loc["lng"],
                "zoom": 11,
                "covered_suburbs": [loc["name"]]
            })
            
    print(f"[+] Spatial clustering complete: Reduced from {len(raw_locations)} to {len(clustered_locations)} optimized coordinate points.")
    
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locations_sk.py")
    print(f"[*] Writing {len(clustered_locations)} clustered locations to {output_path}...")
    
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("# Generated automatically by generate_locations_sk.py\n")
            f.write("# Covers all populated locations in Slovakia using spatial clustering.\n\n")
            f.write("LOCATIONS = [\n")
            for i, loc in enumerate(clustered_locations):
                covered_str = ", ".join(loc["covered_suburbs"][:5])
                if len(loc["covered_suburbs"]) > 5:
                    covered_str += f" and {len(loc['covered_suburbs']) - 5} more"
                
                f.write(f"    # Covers: {covered_str}\n")
                f.write(f"    {{\"state\": \"{loc['state']}\", \"name\": \"{loc['name']}\", \"lat\": {loc['lat']:.6f}, \"lng\": {loc['lng']:.6f}, \"zoom\": 11}}")
                if i < len(clustered_locations) - 1:
                    f.write(",\n")
                else:
                    f.write("\n")
            f.write("]\n\n")
            f.write("def get_locations():\n")
            f.write("    return LOCATIONS\n")
        print("[SUCCESS] locations_sk.py has been successfully created!")
    except Exception as err:
        print(f"[-] Writing failed: {err}")

if __name__ == "__main__":
    main()
