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
    url = "https://simplemaps.com/static/data/country-cities/ie/ie.csv"
    print(f"[*] Downloading Ireland locations database from: {url}")
    
    raw_locations = []
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            csv_data = response.read().decode('utf-8')
            reader = csv.DictReader(io.StringIO(csv_data))
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
                    # Ireland bounding box coordinates check
                    if not (51.4 < lat < 55.4) or not (-10.7 < lng < -5.9):
                        continue
                    
                    raw_locations.append({
                        "state": state if state else "Ireland",
                        "name": locality,
                        "lat": lat,
                        "lng": lng
                    })
                except ValueError:
                    continue
    except Exception as e:
        print(f"[-] Simplemaps download failed ({e}), falling back to built-in Ireland city coordinates...")

    # Built-in fallback Ireland major cities & tourist hubs
    fallback_cities = [
        {"state": "Leinster", "name": "Dublin", "lat": 53.349805, "lng": -6.260310},
        {"state": "Leinster", "name": "Dún Laoghaire", "lat": 53.2944, "lng": -6.1339},
        {"state": "Leinster", "name": "Swords", "lat": 53.4597, "lng": -6.2181},
        {"state": "Leinster", "name": "Tallaght", "lat": 53.2878, "lng": -6.3708},
        {"state": "Leinster", "name": "Bray", "lat": 53.2028, "lng": -6.0983},
        {"state": "Leinster", "name": "Dundalk", "lat": 54.0039, "lng": -6.4022},
        {"state": "Leinster", "name": "Drogheda", "lat": 53.7178, "lng": -6.3478},
        {"state": "Leinster", "name": "Navan", "lat": 53.6528, "lng": -6.6814},
        {"state": "Leinster", "name": "Kilkenny", "lat": 52.6541, "lng": -7.2448},
        {"state": "Leinster", "name": "Wexford", "lat": 52.3369, "lng": -6.4633},
        {"state": "Leinster", "name": "Carlow", "lat": 52.8365, "lng": -6.9261},
        {"state": "Leinster", "name": "Mullingar", "lat": 53.5256, "lng": -7.3389},
        {"state": "Leinster", "name": "Athlone", "lat": 53.4239, "lng": -7.9407},
        {"state": "Leinster", "name": "Tullamore", "lat": 53.2756, "lng": -7.4933},
        {"state": "Leinster", "name": "Naas", "lat": 53.2178, "lng": -6.6669},
        {"state": "Munster", "name": "Cork", "lat": 51.8985, "lng": -8.4756},
        {"state": "Munster", "name": "Cobh", "lat": 51.8503, "lng": -8.2942},
        {"state": "Munster", "name": "Kinsale", "lat": 51.7058, "lng": -8.5306},
        {"state": "Munster", "name": "Mallow", "lat": 52.1389, "lng": -8.6417},
        {"state": "Munster", "name": "Limerick", "lat": 52.6638, "lng": -8.6267},
        {"state": "Munster", "name": "Waterford", "lat": 52.2593, "lng": -7.1101},
        {"state": "Munster", "name": "Killarney", "lat": 52.0599, "lng": -9.5044},
        {"state": "Munster", "name": "Tralee", "lat": 52.2704, "lng": -9.7026},
        {"state": "Munster", "name": "Ennis", "lat": 52.8463, "lng": -8.9811},
        {"state": "Munster", "name": "Clonmel", "lat": 52.3550, "lng": -7.7039},
        {"state": "Munster", "name": "Dungarvan", "lat": 52.0883, "lng": -7.6253},
        {"state": "Connacht", "name": "Galway", "lat": 53.2707, "lng": -9.0568},
        {"state": "Connacht", "name": "Sligo", "lat": 54.2766, "lng": -8.4761},
        {"state": "Connacht", "name": "Castlebar", "lat": 53.8542, "lng": -9.2978},
        {"state": "Connacht", "name": "Westport", "lat": 53.8014, "lng": -9.5236},
        {"state": "Connacht", "name": "Roscommon", "lat": 53.6308, "lng": -8.1919},
        {"state": "Connacht", "name": "Ballina", "lat": 54.1167, "lng": -9.1667},
        {"state": "Ulster", "name": "Letterkenny", "lat": 54.9558, "lng": -7.7347},
        {"state": "Ulster", "name": "Donegal", "lat": 54.6539, "lng": -8.1097},
        {"state": "Ulster", "name": "Monaghan", "lat": 54.2489, "lng": -6.9686},
        {"state": "Ulster", "name": "Cavan", "lat": 53.9908, "lng": -7.3606}
    ]

    if not raw_locations:
        raw_locations = fallback_cities
    else:
        # Merge built-in tourist cities to ensure 100% coverage
        for fc in fallback_cities:
            if not any(calculate_distance(fc["lat"], fc["lng"], r["lat"], r["lng"]) < 5.0 for r in raw_locations):
                raw_locations.append(fc)

    print(f"[+] Loaded {len(raw_locations)} valid Ireland locations.")
    print("[*] Performing spatial clustering to eliminate overlaps (radius ~12.0 km)...")
    
    clustered_locations = []
    threshold_km = 12.0
    
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
            
    print(f"[+] Spatial clustering complete: {len(clustered_locations)} location grid points.")
    
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locations_ie.py")
    print(f"[*] Writing clustered locations to {output_path}...")
    
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("# Generated automatically by generate_locations_ie.py\n")
            f.write("# Covers all populated locations in Ireland using spatial clustering.\n\n")
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
        print("[SUCCESS] locations_ie.py has been successfully created!")
    except Exception as err:
        print(f"[-] Writing failed: {err}")

if __name__ == "__main__":
    main()
