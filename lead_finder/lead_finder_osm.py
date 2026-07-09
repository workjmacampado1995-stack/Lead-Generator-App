"""
Bookkeeping Lead Finder (OpenStreetMap version -- no API key, no credit card)
------------------------------------------------------------------------------
Finds small businesses that are likely candidates for outsourced bookkeeping
services by querying the free OpenStreetMap Overpass API.

Why this version: Google Places requires a credit card on file (even for
free-tier use). OpenStreetMap's Overpass API is completely free, requires
no sign-up, no API key, and no card.

How likelihood is estimated: businesses with no listed website, phone, or
email tend to be smaller/less formalized and may be more likely to need an
outsourced bookkeeper. This is a heuristic, not a guarantee.

Setup:
    1. pip install -r requirements.txt
    2. Run: python lead_finder_osm.py --cities "Los Angeles, California, USA"
       --business-types amenity:restaurant shop:hairdresser
    3. Review the generated CSV file.
"""

import argparse
import csv
import os
import time

import requests

# ---------------------------------------------------------------------------
# CONFIG -- edit this section
# ---------------------------------------------------------------------------

# California cities to search by default. Add as many as you want.
CITIES = [
    "Los Angeles, California, USA",
    "San Diego, California, USA",
    "Sacramento, California, USA",
    "Fresno, California, USA",
]

# OpenStreetMap tags for business types that commonly outsource bookkeeping.
# Format: (tag_key, tag_value, friendly_label)
BUSINESS_TYPES = [
    ("amenity", "restaurant", "restaurant"),
    ("shop", "hairdresser", "hair salon"),
    ("shop", "car_repair", "auto repair shop"),
    ("craft", "electrician", "electrician"),
    ("craft", "plumber", "plumber"),
    ("shop", "clothes", "retail boutique"),
    ("amenity", "cafe", "coffee shop"),
    ("amenity", "dentist", "dental office"),
    ("shop", "hardware", "hardware store"),
    ("amenity", "car_wash", "car wash"),
]

OUTPUT_CSV = "bookkeeping_leads_california.csv"
REQUEST_DELAY = 6  # be polite to the free Overpass servers (raised to avoid 429s)

# ---------------------------------------------------------------------------
# CORE LOGIC
# ---------------------------------------------------------------------------

# Public Overpass API endpoints (free, no key). Falls back to mirrors if one is busy.
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "BookkeepingLeadFinder/1.0 (personal small-business project)"}


def build_parser():
    parser = argparse.ArgumentParser(description="Find small-business leads that may need bookkeeping services")
    parser.add_argument("--cities", nargs="+", default=CITIES, help="Cities to search (for example: 'Los Angeles, California, USA')")
    parser.add_argument(
        "--business-types",
        nargs="+",
        default=[f"{tag_key}:{tag_value}" for tag_key, tag_value, _ in BUSINESS_TYPES],
        help="Business tags to search as key:value pairs (for example: amenity:restaurant)",
    )
    parser.add_argument("--output", default=OUTPUT_CSV, help="CSV file to write")
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY, help="Delay between Overpass requests in seconds")
    return parser


def parse_business_types(raw_values):
    parsed = []
    for entry in raw_values:
        if ":" not in entry:
            print(f"  [!] Skipping invalid business type '{entry}'. Use key:value format.")
            continue
        tag_key, tag_value = entry.split(":", 1)
        parsed.append((tag_key.strip(), tag_value.strip(), tag_value.strip()))
    return parsed


def geocode_city(city_name):
    """Turn a city name into a bounding box using Nominatim (OSM's free geocoder)."""
    params = {"q": city_name, "format": "json", "limit": 1}
    resp = requests.get(NOMINATIM_URL, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    results = resp.json()
    if not results:
        print(f"  [!] Could not geocode '{city_name}'")
        return None
    bbox = results[0]["boundingbox"]  # [south, north, west, east] as strings
    south, north, west, east = map(float, bbox)
    return (south, west, north, east)  # Overpass wants (south, west, north, east)


def query_overpass(tag_key, tag_value, bbox):
    """Query Overpass API for businesses matching a tag within a bounding box."""
    south, west, north, east = bbox
    query = f"""
    [out:json][timeout:25];
    (
      node["{tag_key}"="{tag_value}"]({south},{west},{north},{east});
      way["{tag_key}"="{tag_value}"]({south},{west},{north},{east});
    );
    out center tags;
    """

    for endpoint in OVERPASS_ENDPOINTS:
        for attempt in range(3):  # retry each endpoint up to 3 times if rate-limited
            try:
                resp = requests.post(endpoint, data={"data": query}, headers=HEADERS, timeout=30)
                if resp.status_code == 200:
                    return resp.json().get("elements", [])
                if resp.status_code == 429:
                    wait = 15 * (attempt + 1)  # back off longer each retry
                    print(f"  [!] Rate limited (429) on {endpoint}. Waiting {wait}s before retry...")
                    time.sleep(wait)
                else:
                    print(f"  [!] Overpass endpoint {endpoint} returned {resp.status_code}, trying next...")
                    break  # non-429 error, move to next endpoint instead of retrying
            except requests.RequestException as e:
                print(f"  [!] Overpass endpoint {endpoint} failed: {e}, trying next...")
                break
    return []


def score_lead(website, phone, email):
    """Simple heuristic: missing contact details suggest a smaller/less formal business."""
    score = 0
    if not website:
        score += 3
    if not phone:
        score += 1
    if not email:
        score += 1
    return score


def extract_lead(element, category_label):
    tags = element.get("tags", {})
    name = tags.get("name", "").strip()
    if not name:
        return None  # skip unnamed entries, not useful as leads

    website = tags.get("website", tags.get("contact:website", "")).strip()
    phone = tags.get("phone", tags.get("contact:phone", "")).strip()
    email = tags.get("email", tags.get("contact:email", "")).strip()

    # Build a readable address from whatever OSM fields are present
    addr_parts = [
        tags.get("addr:housenumber", ""),
        tags.get("addr:street", ""),
        tags.get("addr:city", ""),
        tags.get("addr:state", ""),
        tags.get("addr:postcode", ""),
    ]
    address = " ".join(p for p in addr_parts if p)

    return {
        "business_name": name,
        "category_searched": category_label,
        "address": address,
        "phone": phone,
        "website": website,
        "email": email,
        "lead_score": score_lead(website, phone, email),
    }


def run(args):
    all_leads = []
    seen_names_addresses = set()
    business_types = parse_business_types(args.business_types)

    if not business_types:
        print("No valid business types provided. Exiting.")
        return

    for city in args.cities:
        print(f"\nGeocoding '{city}'...")
        bbox = geocode_city(city)
        if not bbox:
            continue
        time.sleep(1)  # be polite to Nominatim (max ~1 request/sec)

        for tag_key, tag_value, label in business_types:
            print(f"  Searching '{label}' in {city}...")
            elements = query_overpass(tag_key, tag_value, bbox)

            for element in elements:
                lead = extract_lead(element, label)
                if not lead:
                    continue
                dedup_key = (lead["business_name"], lead["address"])
                if dedup_key in seen_names_addresses:
                    continue
                seen_names_addresses.add(dedup_key)
                all_leads.append(lead)

            time.sleep(args.delay)  # be polite to the free Overpass servers

    all_leads.sort(key=lambda x: (-x["lead_score"], x["business_name"]))

    if not all_leads:
        print("\nNo leads found. Try different cities or business types.")
        return

    output_dir = os.path.dirname(args.output) or "."
    os.makedirs(output_dir, exist_ok=True)

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_leads[0].keys())
        writer.writeheader()
        writer.writerows(all_leads)

    print(f"\nDone. {len(all_leads)} leads saved to {args.output}")


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    run(args)
