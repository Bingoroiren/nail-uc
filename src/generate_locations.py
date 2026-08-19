import urllib.request
import csv
import io
import os
import math

# Define metropolitan and major urban postcode ranges for each state/territory
METRO_POSTCODES = {
    "NSW": [
        (2000, 2234), # Greater Sydney
        (2250, 2310), # Central Coast / Newcastle
        (2500, 2530)  # Wollongong
    ],
    "ACT": [
        (2600, 2620), # Canberra
        (2900, 2920)  # Canberra Gungahlin / Tuggeranong
    ],
    "VIC": [
        (3000, 3207), # Greater Melbourne
        (3211, 3220)  # Geelong
    ],
    "QLD": [
        (4000, 4179), # Greater Brisbane
        (4208, 4228), # Gold Coast
        (4550, 4575)  # Sunshine Coast
    ],
    "SA": [
        (5000, 5174)  # Adelaide
    ],
    "WA": [
        (6000, 6199)  # Perth
    ],
    "TAS": [
        (7000, 7018)  # Hobart
    ]
}

def is_metro_postcode(state, postcode_str):
    """Verifies if a postcode belongs to the major metropolitan/urban zones."""
    try:
        pc = int(postcode_str)
    except ValueError:
        return False
        
    ranges = METRO_POSTCODES.get(state.upper())
    if not ranges:
        return False
        
    for start, end in ranges:
        if start <= pc <= end:
            return True
    return False

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
    url = "https://raw.githubusercontent.com/schappim/australian-postcodes/master/australian-postcodes.csv"
    print(f"[*] Downloading Australian postcode database from: {url}")
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            csv_data = response.read().decode('utf-8')
    except Exception as e:
        print(f"[-] Download failed: {e}")
        return
        
    print("[*] Parsing CSV and filtering metropolitan suburbs...")
    reader = csv.DictReader(io.StringIO(csv_data))
    
    raw_suburbs = []
    for row in reader:
        # Exclude PO Boxes, LVR (Large Volume Receivers) and virtual postcodes
        category = row.get("Category", "").lower()
        if "box" in category or "lvr" in category or "lvr's" in category:
            continue
            
        locality = row.get("Suburb", "").strip()
        state = row.get("State", "").strip()
        postcode = row.get("Postcode", "").strip()
        lat_str = row.get("Lat", "").strip()
        lng_str = row.get("Lon", "").strip()
        
        if not locality or not state or not lat_str or not lng_str:
            continue
            
        # Restrict to metropolitan and urban postcodes only
        if not is_metro_postcode(state, postcode):
            continue
            
        try:
            lat = float(lat_str)
            lng = float(lng_str)
            if not (-45.0 < lat < -9.0) or not (110.0 < lng < 155.0):
                continue
            
            raw_suburbs.append({
                "state": state,
                "name": locality.title(),
                "lat": lat,
                "lng": lng,
                "postcode": postcode
            })
        except ValueError:
            continue

    print(f"[+] Loaded {len(raw_suburbs)} metropolitan suburbs.")
    print("[*] Performing spatial clustering to eliminate overlaps (radius ~4.5 km)...")
    
    clustered_locations = []
    threshold_km = 4.5
    
    for suburb in raw_suburbs:
        is_covered = False
        for center in clustered_locations:
            dist = calculate_distance(suburb["lat"], suburb["lng"], center["lat"], center["lng"])
            if dist <= threshold_km:
                is_covered = True
                if suburb["name"] not in center["covered_suburbs"]:
                    center["covered_suburbs"].append(suburb["name"])
                break
                
        if not is_covered:
            clustered_locations.append({
                "state": suburb["state"],
                "name": suburb["name"],
                "lat": suburb["lat"],
                "lng": suburb["lng"],
                "zoom": 13,
                "covered_suburbs": [suburb["name"]]
            })
            
    print(f"[+] Spatial clustering complete: Reduced from {len(raw_suburbs)} to {len(clustered_locations)} optimized metropolitan coordinate points.")
    
    # Save the generated locations back into src/locations.py
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locations.py")
    print(f"[*] Writing {len(clustered_locations)} clustered locations to {output_path}...")
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Generated automatically by generate_locations.py\n")
        f.write("# Covers all metropolitan and major urban suburbs in Australia using spatial clustering.\n\n")
        f.write("LOCATIONS = [\n")
        for i, loc in enumerate(clustered_locations):
            covered_str = ", ".join(loc["covered_suburbs"][:5])
            if len(loc["covered_suburbs"]) > 5:
                covered_str += f" and {len(loc['covered_suburbs']) - 5} more"
            
            f.write(f"    # Covers: {covered_str}\n")
            f.write(f"    {{\"state\": \"{loc['state']}\", \"name\": \"{loc['name']}\", \"lat\": {loc['lat']:.6f}, \"lng\": {loc['lng']:.6f}, \"zoom\": 13}}")
            if i < len(clustered_locations) - 1:
                f.write(",\n")
            else:
                f.write("\n")
        f.write("]\n\n")
        f.write("def get_locations():\n")
        f.write("    return LOCATIONS\n")

    print("[SUCCESS] locations.py has been successfully updated with the metropolitan dataset!")

if __name__ == "__main__":
    main()
