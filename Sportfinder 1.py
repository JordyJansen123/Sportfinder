import json
import pandas as pd
import folium
from folium.plugins import MarkerCluster
from branca.element import Element

# =========================
# CONFIG
# =========================
CSV_PATH = "nl_sports_facilities_clean.csv"
OUT_HTML = "nl_sports_map_click_overview.html"
LIMIT = 4000

DEFAULT_RADIUS_KM = 5.5
DEFAULT_MAX_RESULTS = 55

# =========================
# HELPERS
# =========================
def clean_str(x):
    if x is None:
        return ""
    if isinstance(x, float) and pd.isna(x):
        return ""
    return str(x).strip()

def title_from_row(row):
    for k in ("name", "sport", "leisure"):
        v = clean_str(row.get(k))
        if v:
            return v.replace("_", " ").title()
    return "Onbekende locatie"

def popup_html(row):
    return f"""
    <div style="font-family:system-ui;font-size:14px;">
      <b>{title_from_row(row)}</b><br>
      {clean_str(row.get("sport"))} {clean_str(row.get("leisure"))}
    </div>
    """

# =========================
# CLICK OVERVIEW (CORRECT MODEL)
# =========================
def inject_click_overview(m, facilities):
    map_var = m.get_name()
    facilities_json = json.dumps(facilities, ensure_ascii=False)

    html = f"""
    <style>
      .sidebar {{
        position: fixed;
        right: 16px;
        top: 16px;
        width: 380px;
        max-height: calc(100vh - 32px);
        background: white;
        border-radius: 14px;
        box-shadow: 0 12px 30px rgba(0,0,0,.25);
        z-index: 1000;
        padding: 14px;
        overflow: auto;
        font-family: system-ui;
      }}

      .btn {{
        width:100%;
        padding:10px;
        border-radius:10px;
        border:1px solid #ddd;
        background:#f7f7f7;
        cursor:pointer;
        margin-bottom:8px;
        font-weight:600;
      }}

      .btn.active {{
        background:#dbeafe;
        border-color:#60a5fa;
      }}

      .chip {{
        display:inline-block;
        padding:4px 8px;
        border:1px solid #ddd;
        border-radius:999px;
        margin:4px 4px 0 0;
        font-size:12px;
        background:#fafafa;
      }}

      .item {{
        border:1px solid #eee;
        border-radius:10px;
        padding:8px;
        margin-top:8px;
        font-size:13px;
      }}

      .muted {{
        opacity:0.75;
        font-size:12px;
      }}
    </style>

    <div class="sidebar">
      <h3>Sport & activiteiten</h3>

      <button class="btn" id="selectBtn">🎯 Selecteer punt</button>
      <button class="btn" id="randomBtn">🎲 Random punt</button>

      <label>Radius (km)</label>
      <input id="radius" type="number" step="0.5"
             value="{DEFAULT_RADIUS_KM}"
             style="width:100%;margin-bottom:8px;">

      <label>Max resultaten</label>
      <input id="maxResults" type="number" step="5"
             value="{DEFAULT_MAX_RESULTS}"
             style="width:100%;margin-bottom:8px;">

      <div id="status" class="muted">
        Status: klik op “Selecteer punt”
      </div>

      <h4>Overzicht</h4>
      <div id="overview" class="muted">Nog geen data.</div>

      <h4>Locaties</h4>
      <div id="results" class="muted">Nog geen data.</div>
    </div>

    <script>
      const FACILITIES = {facilities_json};
      const MAP = {map_var};

      let selectMode = false;
      let marker = null;
      let circle = null;

      function haversine(lat1, lon1, lat2, lon2) {{
        const R = 6371;
        const dLat = (lat2-lat1)*Math.PI/180;
        const dLon = (lon2-lon1)*Math.PI/180;
        const a =
          Math.sin(dLat/2)**2 +
          Math.cos(lat1*Math.PI/180) *
          Math.cos(lat2*Math.PI/180) *
          Math.sin(dLon/2)**2;
        return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
      }}

      function analyze(lat, lon) {{
        const radius = parseFloat(document.getElementById("radius").value);
        const maxResults = parseInt(document.getElementById("maxResults").value);

        if (marker) MAP.removeLayer(marker);
        if (circle) MAP.removeLayer(circle);

        marker = L.marker([lat, lon]).addTo(MAP);
        circle = L.circle([lat, lon], {{
          radius: radius * 1000,
          fillOpacity: 0.08,
          weight: 1
        }}).addTo(MAP);

        let hits = [];
        for (const f of FACILITIES) {{
          const d = haversine(lat, lon, f.lat, f.lon);
          if (d <= radius) hits.push({{...f, dist:d}});
        }}
        hits.sort((a,b)=>a.dist-b.dist);

        document.getElementById("status").innerHTML =
          `Punt gekozen: <b>${{lat.toFixed(4)}}, ${{lon.toFixed(4)}}</b><br>
           Locaties: <b>${{hits.length}}</b>`;

        const counts = {{}};
        for (const h of hits) {{
          if (h.sport) counts[h.sport] = (counts[h.sport]||0)+1;
          if (h.leisure) counts[h.leisure] = (counts[h.leisure]||0)+1;
        }}

        document.getElementById("overview").innerHTML =
          Object.entries(counts)
            .sort((a,b)=>b[1]-a[1])
            .map(x=>`<span class="chip">${{x[0]}} (${{x[1]}})</span>`)
            .join("") || "Geen activiteiten gevonden.";

        document.getElementById("results").innerHTML =
          hits.slice(0, maxResults).map(h=>`
            <div class="item">
              <b>${{h.title}}</b><br>
              ${{h.sport||""}} ${{h.leisure||""}}<br>
              ${{h.dist.toFixed(2)}} km<br>
              <a target="_blank"
                 href="https://www.google.com/maps?q=${{h.lat}},${{h.lon}}">
                 Google Maps
              </a>
            </div>
          `).join("") || "Geen locaties.";
      }}

      // 🔑 KAART KLIK – alleen actief in selectiemodus
      MAP.on("click", function(e) {{
        if (!selectMode) return;
        selectMode = false;
        document.getElementById("selectBtn").classList.remove("active");
        analyze(e.latlng.lat, e.latlng.lng);
      }});

      document.getElementById("selectBtn").onclick = function() {{
        selectMode = !selectMode;
        this.classList.toggle("active", selectMode);
        document.getElementById("status").innerHTML =
          selectMode
            ? "Selectiemodus actief: klik ergens op de kaart"
            : "Selectiemodus uit";
      }};

      document.getElementById("randomBtn").onclick = function() {{
        const bounds = MAP.getBounds();
        const lat = bounds.getSouth() + Math.random() * (bounds.getNorth() - bounds.getSouth());
        const lon = bounds.getWest() + Math.random() * (bounds.getEast() - bounds.getWest());
        analyze(lat, lon);
      }};
    </script>
    """

    m.get_root().html.add_child(Element(html))

# =========================
# MAIN
# =========================
def main():
    df = pd.read_csv(CSV_PATH).head(LIMIT)

    m = folium.Map(location=[52.1, 5.3], zoom_start=8, control_scale=True)
    cluster = MarkerCluster().add_to(m)

    facilities = []

    for _, row in df.iterrows():
        lat, lon = row.get("lat"), row.get("lon")
        if pd.isna(lat) or pd.isna(lon):
            continue

        folium.CircleMarker(
            [lat, lon],
            radius=6,
            popup=popup_html(row),
            fill=True
        ).add_to(cluster)

        facilities.append({
            "lat": float(lat),
            "lon": float(lon),
            "title": title_from_row(row),
            "sport": clean_str(row.get("sport")),
            "leisure": clean_str(row.get("leisure")),
        })

    inject_click_overview(m, facilities)
    m.save(OUT_HTML)
    print("Kaart opgeslagen:", OUT_HTML)

if __name__ == "__main__":
    main()
