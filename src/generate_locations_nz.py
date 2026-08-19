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
    url = "https://gist.githubusercontent.com/ian-patel/2d8f0c0d613334e546a83df9ea2e869c/raw/"
    print(f"[*] Downloading New Zealand locations database from: {url}")
    
    csv_data = None
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            csv_data = response.read().decode('utf-8')
    except Exception as e:
        print(f"[-] Download failed: {e}")
        # Try local fallback from step artifact if running inside this agent context
        fallback_path = r"C:\Users\Admin\.gemini\antigravity-ide\brain\26fad064-dd74-4246-809e-0e13b7e9c98b\.system_generated\steps\39\content.md"
        if os.path.exists(fallback_path):
            print(f"[*] Trying fallback local file: {fallback_path}")
            with open(fallback_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                # Find start of CSV
                csv_start = 0
                for idx, line in enumerate(lines):
                    if "ItemID,Location,Latitude,Longitude" in line:
                        csv_start = idx
                        break
                csv_data = "".join(lines[csv_start:])
        else:
            print("[-] No fallback file found. Exiting.")
            return
        
    print("[*] Parsing CSV data...")
    reader = csv.DictReader(io.StringIO(csv_data))
    
    raw_locations = []
    for row in reader:
        location_name = row.get("Location", "").strip()
        lat_str = row.get("Latitude", "").strip()
        lng_str = row.get("Longitude", "").strip()
        
        if not location_name or not lat_str or not lng_str:
            continue
            
        try:
            lat = float(lat_str)
            lng = float(lng_str)
            
            # New Zealand boundary check
            if not (-48.0 < lat < -34.0) or not (165.0 < lng < 179.5):
                continue
                
            raw_locations.append({
                "name": location_name.title(),
                "lat": lat,
                "lng": lng
            })
        except ValueError:
            continue

    print(f"[+] Loaded {len(raw_locations)} valid New Zealand locations.")
    print("[*] Performing spatial clustering to eliminate overlaps (radius ~20.0 km)...")
    
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
                "name": loc["name"],
                "lat": loc["lat"],
                "lng": loc["lng"],
                "zoom": 11,
                "covered_suburbs": [loc["name"]]
            })
            
    print(f"[+] Spatial clustering complete: Reduced from {len(raw_locations)} to {len(clustered_locations)} optimized coordinate points.")
    
    # Save the generated locations back into src/locations_nz.py
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locations_nz.py")
    print(f"[*] Writing {len(clustered_locations)} clustered locations to {output_path}...")
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Generated automatically by generate_locations_nz.py\n")
        f.write("# Covers major cities and towns in New Zealand using spatial clustering.\n\n")
        f.write("LOCATIONS = [\n")
        for i, loc in enumerate(clustered_locations):
            covered_str = ", ".join(loc["covered_suburbs"][:5])
            if len(loc["covered_suburbs"]) > 5:
                covered_str += f" and {len(loc['covered_suburbs']) - 5} more"
            
            f.write(f"    # Covers: {covered_str}\n")
            # State is omitted or kept as empty for NZ
            f.write(f"    {{\"state\": \"NZ\", \"name\": \"{loc['name']}\", \"lat\": {loc['lat']:.6f}, \"lng\": {loc['lng']:.6f}, \"zoom\": {loc['zoom']}}}")
            if i < len(clustered_locations) - 1:
                f.write(",\n")
            else:
                f.write("\n")
        f.write("]\n\n")
        f.write("def get_locations():\n")
        f.write("    return LOCATIONS\n")

    print("[SUCCESS] locations_nz.py has been successfully updated with the New Zealand dataset!")

if __name__ == "__main__":
    main()
