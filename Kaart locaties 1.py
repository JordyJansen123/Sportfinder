import re
import time
import json
import os
import pandas as pd
import requests
from bs4 import BeautifulSoup
import folium
from folium.plugins import MarkerCluster

# =========================
# CONFIG
# =========================
CSV_PATH = "nl_sports_facilities_clean.csv"
OUT_HTML = "nl_sports_map_top_4000_links_prices_google_hours.html"
LIMIT = 4000  # top 4000 locaties

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

# =========================
# GOOGLE (REST) CONFIG
# =========================
GOOGLE_API_KEY = "PASTE_YOUR_NEW_API_KEY_HERE"

GOOGLE_MAX_REQUESTS = 10_000
GOOGLE_CACHE_FILE = "google_places_cache.json"
GOOGLE_SLEEP_SECONDS = 0.10  # netjes

# Wanneer Google gebruiken?
# - We gebruiken Google alleen als openingstijden ontbreken OF als er geen enkele link is.
USE_GOOGLE_IF_MISSING_HOURS = True
USE_GOOGLE_IF_MISSING_LINKS = True

# =========================
# Utrecht configuratie
# =========================
UTRECHT_INFO_URL = "https://www.utrecht.nl/wonen-en-leven/vrije-tijd/sport/sportlocaties/sportzalen-en-gymzalen-huren"
UTRECHT_BOOKING_URL = "https://asp5.lvp.nl/amisweb/utrecht/amis1/amis.php?action=schema1"
UTRECHT_FROM_PRICE_TEXT = "In het weekend al vanaf €8,40 per uur."
UTRECHT_MUNICIPALITY_CITIES = {"utrecht", "vleuten", "de meern"}

# =========================
# KETENS + PRIJSBRONNEN
# =========================
CHAIN_KEYWORDS = {
    "Basic-Fit": ["basic fit", "basic-fit"],
    "SportCity": ["sportcity", "sport city"],
    "Anytime Fitness": ["anytime fitness"],
    "Fit For Free": ["fit for free"],
    "TrainMore": ["trainmore", "train more"],
    "Snap Fitness": ["snap fitness"],
    "Jetts Fitness": ["jetts"],
    "Curves": ["curves"],
    "Fit20": ["fit20", "fit 20"],
}

CHAIN_PRICE_SOURCES = {
    "Basic-Fit": [
        "https://www.basic-fit.com/nl-nl/abonnementen",
        "https://www.basic-fit.com/nl-nl"
    ],
    "SportCity": [
        "https://www.sportcity.nl/abonnementen",
        "https://www.sportcity.nl"
    ],
    "Anytime Fitness": [
        "https://www.anytimefitness.nl",
    ],
    "Fit For Free": [
        "https://www.fitforfree.nl",
    ],
    "TrainMore": [
        "https://trainmore.nl",
    ],
    "Snap Fitness": [
        "https://www.snapfitness.com/nl",
    ],
    "Jetts Fitness": [
        "https://www.jetts.com/nl",
    ],
    "Curves": [
        "https://www.curves.eu/nl",
    ],
    "Fit20": [
        "https://fit20.nl",
    ],
}

_price_regex = re.compile(
    r"(vanaf\s*)?€\s?\d{1,3}(?:[.,]\d{2})?\s*(?:per|/)\s*(?:4\s*weken|maand|week|jaar|dagen|dag|bezoek|bezoeken)",
    re.IGNORECASE
)

# =========================
# HELPERS
# =========================
def clean_str(x):
    if x is None:
        return ""
    if isinstance(x, float) and pd.isna(x):
        return ""
    s = str(x).strip()
    if s.lower() == "nan":
        return ""
    return s

def normalize_name(s: str) -> str:
    s = clean_str(s).lower()
    s = re.sub(r"[\u2019’]", "'", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def strip_trailing_number(name_norm: str) -> str:
    return re.sub(r"\s+\d+[a-z]?$", "", name_norm).strip()

def title_from_row(row):
    name = clean_str(row.get("name"))
    sport = clean_str(row.get("sport"))
    leisure = clean_str(row.get("leisure"))
    if name:
        return name
    if sport:
        return sport.title()
    if leisure:
        return leisure.replace("_", " ").title()
    return "Onbekende locatie"

def subtitle_from_row(row):
    sport = clean_str(row.get("sport"))
    leisure = clean_str(row.get("leisure"))
    parts = [p for p in [sport, leisure] if p]
    if not parts:
        return ""
    return " • ".join([p.replace("_", " ").title() for p in parts])

def guess_chain(name, brand):
    name_l = clean_str(name).lower()
    brand_l = clean_str(brand).lower()
    for chain, kws in CHAIN_KEYWORDS.items():
        for kw in kws:
            if kw in name_l or kw in brand_l:
                return chain
    return ""

def ensure_http(url: str) -> str:
    u = clean_str(url)
    if not u:
        return ""
    if u.startswith(("http://", "https://")):
        return u
    if u.startswith("www."):
        return "https://" + u
    if "." in u:
        return "https://" + u
    return ""

# =========================
# LINKS UIT CSV (geen Google nodig)
# =========================
def collect_links_from_row(row):
    # Voeg hier gerust kolommen toe die jij in je CSV ziet
    link_cols = [
        "website",
        "url",
        "contact:website",
        "contact:url",
        "contact:facebook",
        "contact:instagram",
        "contact:twitter",
        "facebook",
        "instagram",
        "twitter",
    ]

    links = []
    for col in link_cols:
        if col in row and row.get(col) is not None:
            raw = clean_str(row.get(col))
            if not raw:
                continue
            # soms meerdere links in één cel
            parts = re.split(r"[,\s]+", raw)
            for p in parts:
                p = ensure_http(p)
                if p:
                    links.append((col, p))

    # uniek
    seen = set()
    uniq = []
    for label, url in links:
        k = url.lower()
        if k in seen:
            continue
        seen.add(k)
        uniq.append((label, url))
    return uniq

# =========================
# KETEN PRIJZEN
# =========================
def scrape_price_text(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return ""
        html = r.text

        m = _price_regex.search(html)
        if m:
            return " ".join(m.group(0).split())

        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True)
        m2 = _price_regex.search(text)
        if m2:
            return " ".join(m2.group(0).split())

        return ""
    except Exception:
        return ""

def get_chain_prices():
    prices = {}
    for chain, urls in CHAIN_PRICE_SOURCES.items():
        found = ""
        for u in urls:
            found = scrape_price_text(u)
            if found:
                break
            time.sleep(0.7)
        prices[chain] = found
    return prices

# =========================
# UTRECHT MATCHING
# =========================
def fetch_utrecht_rentable_names_from_booking() -> set[str]:
    try:
        r = requests.get(UTRECHT_BOOKING_URL, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return set()

        soup = BeautifulSoup(r.text, "html.parser")
        options = [opt.get_text(" ", strip=True) for opt in soup.find_all("option")]

        prefixes = ("Gymzaal ", "Sportzaal ", "Sporthal ", "Turnzaal ", "Atletiekbaan ")
        locaties = []
        for t in options:
            if not t or t.strip().startswith("---"):
                continue
            if t.startswith(prefixes):
                locaties.append(t)

        return {normalize_name(x) for x in locaties}
    except Exception:
        return set()

def is_utrecht_rentable_title(title: str, utrecht_rentable_set: set[str]) -> bool:
    t = normalize_name(title)
    t2 = strip_trailing_number(t)

    if t in utrecht_rentable_set or t2 in utrecht_rentable_set:
        return True

    for r in utrecht_rentable_set:
        r2 = strip_trailing_number(r)
        if t == r2 or t2 == r2:
            return True

    return False

# =========================
# GOOGLE CACHE + REQUEST LIMIT
# =========================
def load_google_cache():
    if not os.path.exists(GOOGLE_CACHE_FILE):
        return {"_meta": {"requests_made": 0}, "data": {}}
    try:
        with open(GOOGLE_CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
        cache.setdefault("_meta", {}).setdefault("requests_made", 0)
        cache.setdefault("data", {})
        return cache
    except Exception:
        return {"_meta": {"requests_made": 0}, "data": {}}

def save_google_cache(cache):
    with open(GOOGLE_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

def google_request_allowed(cache) -> bool:
    if not GOOGLE_API_KEY or "PASTE_" in GOOGLE_API_KEY:
        return False
    return cache["_meta"]["requests_made"] < GOOGLE_MAX_REQUESTS

def google_count_request(cache, n=1):
    cache["_meta"]["requests_made"] += n

def google_find_place_id(name, city, cache):
    url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
    params = {
        "input": f"{name} {city}".strip(),
        "inputtype": "textquery",
        "fields": "place_id",
        "language": "nl",
        "key": GOOGLE_API_KEY,
    }
    r = requests.get(url, params=params, timeout=15)
    google_count_request(cache, 1)
    data = r.json()
    candidates = data.get("candidates", [])
    return candidates[0]["place_id"] if candidates else ""

def google_get_place_details(place_id, cache):
    """
    Haalt website + google maps url + openingstijden op.
    opening_hours.weekday_text is het handigst voor jouw popup.
    """
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields": "website,url,opening_hours,name",
        "language": "nl",
        "key": GOOGLE_API_KEY,
    }
    r = requests.get(url, params=params, timeout=15)
    google_count_request(cache, 1)
    data = r.json()
    result = data.get("result", {}) or {}

    opening = ""
    oh = result.get("opening_hours", {}) or {}
    weekday_text = oh.get("weekday_text", [])
    if isinstance(weekday_text, list) and weekday_text:
        opening = " | ".join(weekday_text)  # compact (evt. later mooier met <br>)
    return {
        "website": result.get("website", "") or "",
        "gmaps_url": result.get("url", "") or "",
        "opening_hours": opening,
        "name": result.get("name", "") or "",
    }

def get_google_enrichment(title, city, cache):
    """
    Cache-key op basis van title|city.
    Per nieuwe hit: max 2 requests.
    """
    key = normalize_name(f"{title}|{city}")
    if key in cache["data"]:
        return cache["data"][key] or {}

    if not google_request_allowed(cache):
        cache["data"][key] = {}
        return {}

    place_id = google_find_place_id(title, city, cache)
    time.sleep(GOOGLE_SLEEP_SECONDS)
    if not place_id:
        cache["data"][key] = {}
        return {}

    details = google_get_place_details(place_id, cache)
    time.sleep(GOOGLE_SLEEP_SECONDS)

    cache["data"][key] = details
    return details

# =========================
# POPUP
# =========================
def popup_html(row, chain_prices, utrecht_rentable_set, google_cache):
    title = title_from_row(row)
    subtitle = subtitle_from_row(row)

    street = clean_str(row.get("addr_street"))
    nr = clean_str(row.get("addr_housenumber"))
    pc = clean_str(row.get("addr_postcode"))
    city = clean_str(row.get("addr_city"))
    opening_csv = clean_str(row.get("opening_hours"))

    address_line1 = " ".join([p for p in [street, nr] if p]).strip()
    address_line2 = " ".join([p for p in [pc, city] if p]).strip()

    # Links uit CSV
    links = collect_links_from_row(row)

    # Bepaal of we Google mogen/gaan gebruiken
    need_google_for_hours = USE_GOOGLE_IF_MISSING_HOURS and not opening_csv
    need_google_for_links = USE_GOOGLE_IF_MISSING_LINKS and (len(links) == 0)

    opening_final = opening_csv
    google_links_extra = []
    if (need_google_for_hours or need_google_for_links) and city:
        g = get_google_enrichment(title, city, google_cache)

        # openingstijden aanvullen
        if need_google_for_hours and g.get("opening_hours"):
            opening_final = g["opening_hours"]

        # links aanvullen (website/gmaps)
        if need_google_for_links:
            w = ensure_http(g.get("website", ""))
            u = g.get("gmaps_url", "")
            if w:
                google_links_extra.append(("google_website", w))
            if u:
                google_links_extra.append(("google_maps", u))

    # voeg extra links toe (uniek)
    if google_links_extra:
        existing = {u.lower() for _, u in links}
        for label, url in google_links_extra:
            if url.lower() not in existing:
                links.append((label, url))
                existing.add(url.lower())

    # Keten prijs (indien keten)
    chain = guess_chain(row.get("name"), row.get("brand"))
    chain_price = chain_prices.get(chain, "") if chain else ""

    lines = []
    lines.append("<div style='font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; font-size: 14px;'>")
    lines.append(f"<div style='font-size: 20px; font-weight: 700; margin-bottom: 6px;'>{title}</div>")

    if subtitle:
        lines.append(f"<div style='font-size: 14px; margin-bottom: 8px;'>{subtitle}</div>")

    if address_line1:
        lines.append(f"<div>{address_line1}</div>")
    if address_line2:
        lines.append(f"<div style='margin-bottom: 8px;'>{address_line2}</div>")

    if opening_final:
        lines.append(f"<div><b>Openingstijden:</b> {opening_final}</div>")

    # Utrecht verhuur (alleen als match met officiële lijst)
    if city.lower() in UTRECHT_MUNICIPALITY_CITIES:
        if is_utrecht_rentable_title(title, utrecht_rentable_set):
            lines.append("<div style='margin-top: 8px; padding-top: 8px; border-top: 1px solid #e6e6e6;'>")
            lines.append("<div><b>Te huur (Gemeente Utrecht):</b></div>")
            lines.append(f"<div>{UTRECHT_FROM_PRICE_TEXT}</div>")
            lines.append(
                f"<div style='margin-top: 6px;'><a href='{UTRECHT_INFO_URL}' target='_blank'>Meer info</a> | "
                f"<a href='{UTRECHT_BOOKING_URL}' target='_blank'>Reserveren</a></div>"
            )
            lines.append("</div>")

    # Links
    if links:
        lines.append("<div style='margin-top: 8px; padding-top: 8px; border-top: 1px solid #e6e6e6;'>")
        lines.append("<div><b>Links:</b></div>")
        for label, url in links[:5]:
            show = url
            lines.append(f"<div><a href='{url}' target='_blank'>{show}</a></div>")
        lines.append("</div>")

    # Prijs (keten)
    if chain and chain_price:
        lines.append(f"<div style='margin-top: 8px;'><b>Prijs ({chain}):</b> {chain_price}</div>")

    lines.append("</div>")
    return "\n".join(lines)

# =========================
# MAIN
# =========================
def main():
    df = pd.read_csv(CSV_PATH, low_memory=False).head(LIMIT).copy()
    print(f"Loaded {len(df)} rows (top {LIMIT})")

    # Google cache
    google_cache = load_google_cache()
    print(f"Google requests used so far: {google_cache['_meta']['requests_made']}/{GOOGLE_MAX_REQUESTS}")

    # Ketenprijzen
    print("Scraping keten-prijzen (best effort)...")
    chain_prices = get_chain_prices()
    print("Gevonden ketenprijzen:")
    print(json.dumps(chain_prices, indent=2, ensure_ascii=False))

    # Utrecht lijst
    print("Ophalen Utrecht-lijst met verhuurlocaties (boekingssysteem)...")
    utrecht_rentable_set = fetch_utrecht_rentable_names_from_booking()
    print(f"Utrecht verhuurlocaties gevonden (aantal): {len(utrecht_rentable_set)}")

    # Center map
    df_valid = df.dropna(subset=["lat", "lon"])
    center = [df_valid["lat"].mean(), df_valid["lon"].mean()] if len(df_valid) else [52.1326, 5.2913]

    m = folium.Map(location=center, zoom_start=8, control_scale=True, tiles="OpenStreetMap")
    cluster = MarkerCluster().add_to(m)

    for _, row in df.iterrows():
        lat = row.get("lat")
        lon = row.get("lon")
        if pd.isna(lat) or pd.isna(lon):
            continue

        html = popup_html(row, chain_prices, utrecht_rentable_set, google_cache)
        popup = folium.Popup(html, max_width=420)

        folium.CircleMarker(
            location=[float(lat), float(lon)],
            radius=8,
            popup=popup,
            tooltip=title_from_row(row),
            fill=True,
            fill_opacity=0.9,
            weight=1
        ).add_to(cluster)

    # save cache + map
    save_google_cache(google_cache)
    print(f"Google requests used total: {google_cache['_meta']['requests_made']}/{GOOGLE_MAX_REQUESTS}")
    print(f"Saved map: {OUT_HTML}")

    m.save(OUT_HTML)

if __name__ == "__main__":
    main()
