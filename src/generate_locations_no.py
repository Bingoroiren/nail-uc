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

FALLBACK_NORWAY_LOCATIONS = [
    # Rogaland (Primary agriculture, dairy, livestock & aquaculture district)
    {"state": "Rogaland", "name": "Stavanger", "lat": 58.9700, "lng": 5.7331},
    {"state": "Rogaland", "name": "Sandnes", "lat": 58.8525, "lng": 5.7331},
    {"state": "Rogaland", "name": "Bryne", "lat": 58.7353, "lng": 5.6478},
    {"state": "Rogaland", "name": "Eigersund", "lat": 58.4517, "lng": 6.0003},
    {"state": "Rogaland", "name": "Haugesund", "lat": 59.4138, "lng": 5.2680},
    {"state": "Rogaland", "name": "Hjelmeland", "lat": 59.2333, "lng": 6.1833},

    # Viken / Akershus / Østfold / Buskerud
    {"state": "Viken", "name": "Oslo", "lat": 59.9139, "lng": 10.7522},
    {"state": "Viken", "name": "Drammen", "lat": 59.7441, "lng": 10.2045},
    {"state": "Viken", "name": "Fredrikstad", "lat": 59.2181, "lng": 10.9298},
    {"state": "Viken", "name": "Sarpsborg", "lat": 59.2839, "lng": 11.1096},
    {"state": "Viken", "name": "Moss", "lat": 59.4340, "lng": 10.6577},
    {"state": "Viken", "name": "Ås", "lat": 59.6644, "lng": 10.7967},
    {"state": "Viken", "name": "Eidsvoll", "lat": 60.3300, "lng": 11.2400},
    {"state": "Viken", "name": "Ringerike", "lat": 60.1667, "lng": 10.2500},
    {"state": "Viken", "name": "Indre Østfold", "lat": 59.6000, "lng": 11.3300},

    # Innlandet (Grain, dairy & vegetable farming)
    {"state": "Innlandet", "name": "Hamar", "lat": 60.7945, "lng": 11.0680},
    {"state": "Innlandet", "name": "Lillehammer", "lat": 61.1153, "lng": 10.4662},
    {"state": "Innlandet", "name": "Gjøvik", "lat": 60.7954, "lng": 10.6916},
    {"state": "Innlandet", "name": "Elverum", "lat": 60.8817, "lng": 11.5628},
    {"state": "Innlandet", "name": "Ringsaker", "lat": 60.9000, "lng": 10.7000},
    {"state": "Innlandet", "name": "Stange", "lat": 60.7167, "lng": 11.1833},
    {"state": "Innlandet", "name": "Tynset", "lat": 62.2747, "lng": 10.7783},

    # Vestfold og Telemark (Fruit, berry & vegetable farming)
    {"state": "Vestfold og Telemark", "name": "Tønsberg", "lat": 59.2675, "lng": 10.4078},
    {"state": "Vestfold og Telemark", "name": "Sandefjord", "lat": 59.1312, "lng": 10.2167},
    {"state": "Vestfold og Telemark", "name": "Larvik", "lat": 59.0536, "lng": 10.0350},
    {"state": "Vestfold og Telemark", "name": "Skien", "lat": 59.2096, "lng": 9.6090},
    {"state": "Vestfold og Telemark", "name": "Porsgrunn", "lat": 59.1406, "lng": 9.6561},
    {"state": "Vestfold og Telemark", "name": "Bø i Telemark", "lat": 59.4128, "lng": 9.0686},

    # Vestland (Fruit orchards in Hardanger & salmon/aquaculture)
    {"state": "Vestland", "name": "Bergen", "lat": 60.3913, "lng": 5.3221},
    {"state": "Vestland", "name": "Ullensvang", "lat": 60.3667, "lng": 6.6833},
    {"state": "Vestland", "name": "Voss", "lat": 60.6289, "lng": 6.4153},
    {"state": "Vestland", "name": "Førde", "lat": 61.4522, "lng": 5.8572},
    {"state": "Vestland", "name": "Sogndal", "lat": 61.2306, "lng": 7.1008},
    {"state": "Vestland", "name": "Florø", "lat": 61.5997, "lng": 5.0328},
    {"state": "Vestland", "name": "Austevoll", "lat": 60.0833, "lng": 5.2333}, # Salmon aquaculture hub
    {"state": "Møre og Romsdal", "name": "Ålesund", "lat": 62.4722, "lng": 6.1549},
    {"state": "Møre og Romsdal", "name": "Molde", "lat": 62.7372, "lng": 7.1591},
    {"state": "Møre og Romsdal", "name": "Kristiansund", "lat": 63.1106, "lng": 7.7281},

    # Agder
    {"state": "Agder", "name": "Kristiansand", "lat": 58.1467, "lng": 7.9956},
    {"state": "Agder", "name": "Arendal", "lat": 58.4614, "lng": 8.7726},
    {"state": "Agder", "name": "Grimstad", "lat": 58.3406, "lng": 8.5936},
    {"state": "Agder", "name": "Flekkefjord", "lat": 58.2972, "lng": 6.6606},

    # Trøndelag (Agriculture & major aquaculture)
    {"state": "Trøndelag", "name": "Trondheim", "lat": 63.4305, "lng": 10.3951},
    {"state": "Trøndelag", "name": "Steinkjer", "lat": 64.0149, "lng": 11.4954},
    {"state": "Trøndelag", "name": "Stjørdal", "lat": 63.4681, "lng": 10.9262},
    {"state": "Trøndelag", "name": "Levanger", "lat": 63.7464, "lng": 11.2997},
    {"state": "Trøndelag", "name": "Namsos", "lat": 64.4662, "lng": 11.4958},
    {"state": "Trøndelag", "name": "Hitra", "lat": 63.6000, "lng": 8.8000},
    {"state": "Trøndelag", "name": "Frøya", "lat": 63.7333, "lng": 8.8333}, # Major salmon farming hub

    # Nordland & Troms og Finnmark (Aquaculture & coastal fish farming)
    {"state": "Nordland", "name": "Bodø", "lat": 67.2804, "lng": 14.4050},
    {"state": "Nordland", "name": "Mo i Rana", "lat": 66.3128, "lng": 14.1428},
    {"state": "Nordland", "name": "Narvik", "lat": 68.4385, "lng": 17.4272},
    {"state": "Nordland", "name": "Leknes", "lat": 68.1472, "lng": 13.6114},
    {"state": "Nordland", "name": "Sortland", "lat": 68.6961, "lng": 15.4131},
    {"state": "Troms og Finnmark", "name": "Tromsø", "lat": 69.6492, "lng": 18.9553},
    {"state": "Troms og Finnmark", "name": "Harstad", "lat": 68.7986, "lng": 16.5419},
    {"state": "Troms og Finnmark", "name": "Alta", "lat": 69.9689, "lng": 23.2716},
    {"state": "Troms og Finnmark", "name": "Hammerfest", "lat": 70.6634, "lng": 23.6821}
]

def main():
    url = "https://simplemaps.com/static/data/country-cities/no/no.csv"
    print(f"[*] Downloading Norway locations database from: {url}")
    
    raw_locations = list(FALLBACK_NORWAY_LOCATIONS)
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
                        if 57.9 < lat < 71.2 and 4.5 < lng < 31.2:
                            raw_locations.append({
                                "state": state if state else "Norway",
                                "name": locality,
                                "lat": lat,
                                "lng": lng
                            })
                    except ValueError:
                        pass
        print(f"[+] Combined with online cities dataset. Total raw locations: {len(raw_locations)}")
    except Exception as e:
        print(f"[-] Online download failed ({e}). Using curated fallback Norway locations dataset.")

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
    
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locations_no.py")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Generated automatically for Norway Farms & Aquaculture Scraper\n")
        f.write("# Covers all Norway counties with spatial clustering (zoom level 11)\n\n")
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
