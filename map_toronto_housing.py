"""
Toronto Affordable Housing Map
--------------------------------
Reads the geocoded CSV produced by geocode_toronto_housing.py and
renders an interactive Leaflet map as a standalone HTML file.

Usage:
    pip install pandas requests
    python map_toronto_housing.py
"""

import os
import json
import requests
import pandas as pd

DATA_DIR    = "data"
INPUT_FILE  = os.path.join(DATA_DIR, "subsidized_buildings_geocoded.csv")
OUTPUT_FILE = os.path.join(DATA_DIR, "toronto_housing_map.html")

APPLY_URL              = "https://www.toronto.ca/community-people/employment-social-support/housing-support/rent-geared-to-income-subsidy/"
COHB_URL               = "https://www.toronto.ca/community-people/employment-social-support/housing-support/canada-ontario-housing-benefit/"
TCHC_AFFORDABLE_URL    = "https://torontohousing.ca/prospective-tenants/affordable-rent"
CKAN_WAITLIST_RESOURCE = "f8d91828-86dd-42bd-bb0b-0a8e963b6a02"
CKAN_BASE              = "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action"

WARD_NAMES = {
    "1":"Etobicoke North","2":"Etobicoke Centre","3":"Etobicoke–Lakeshore",
    "4":"Parkdale–High Park","5":"York South–Weston","6":"York Centre",
    "7":"Humber River–Black Creek","8":"Eglinton–Lawrence","9":"Davenport",
    "10":"Spadina–Fort York","11":"University–Rosedale","12":"Toronto–St. Paul's",
    "13":"Toronto Centre","14":"Toronto–Danforth","15":"Don Valley West",
    "16":"Don Valley East","17":"Don Valley North","18":"Willowdale",
    "19":"Beaches–East York","20":"Scarborough Southwest","21":"Scarborough Centre",
    "22":"Scarborough–Agincourt","23":"Scarborough North","24":"Scarborough–Guildwood",
    "25":"Scarborough–Rouge Park",
}


# ── Data prep ─────────────────────────────────────────────────────────────────

def fetch_waitlist_stats() -> dict | None:
    try:
        resp = requests.get(
            f"{CKAN_BASE}/datastore_search",
            params={"resource_id": CKAN_WAITLIST_RESOURCE, "limit": 100},
            timeout=15,
        )
        resp.raise_for_status()
        records = resp.json()["result"]["records"]
        if not records:
            return None
        return {"latest": records[-1], "previous": records[-2] if len(records) >= 2 else None}
    except Exception as e:
        print(f"  Could not fetch waitlist stats: {e}")
        return None


def prepare_buildings(df: pd.DataFrame) -> list[dict]:
    df = df.where(pd.notna(df), None)
    df["Ward"] = df["Ward"].apply(lambda v: str(int(v)) if v is not None else None)
    return df.to_dict(orient="records")


def get_filter_options(buildings: list[dict]) -> dict:
    wards = sorted(
        {b["Ward"] for b in buildings if b.get("Ward")},
        key=int,
    )
    mandates = sorted({
        str(b.get("Building Mandate1") or "").strip()
        for b in buildings
        if str(b.get("Building Mandate1") or "").strip()
    })
    provider_types = sorted({b.get("Provider Type") for b in buildings if b.get("Provider Type")})
    btypes: set[str] = set()
    for b in buildings:
        for t in str(b.get("Building Type") or "").split("|"):
            if t.strip():
                btypes.add(t.strip())
    return {
        "wards":         wards,
        "wardNames":     WARD_NAMES,
        "mandates":      mandates,
        "providerTypes": provider_types,
        "buildingTypes": sorted(btypes),
    }


# ── HTML generation ───────────────────────────────────────────────────────────

def build_html(buildings: list[dict], waitlist: dict | None) -> str:
    options = get_filter_options(buildings)
    html = HTML_TEMPLATE
    html = html.replace("__BUILDINGS__",  json.dumps(buildings,  ensure_ascii=False))
    html = html.replace("__WAITLIST__",   json.dumps(waitlist,   ensure_ascii=False) if waitlist else "null")
    html = html.replace("__OPTIONS__",    json.dumps(options,    ensure_ascii=False))
    html = html.replace("__APPLY_URL__",           json.dumps(APPLY_URL,           ensure_ascii=False))
    html = html.replace("__COHB_URL__",            json.dumps(COHB_URL,            ensure_ascii=False))
    html = html.replace("__TCHC_AFFORDABLE_URL__", json.dumps(TCHC_AFFORDABLE_URL, ensure_ascii=False))
    return html


# ── Entry point ───────────────────────────────────────────────────────────────

def run():
    if not os.path.exists(INPUT_FILE):
        print(f"No data found at {INPUT_FILE}")
        print("Run geocode_toronto_housing.py first.")
        return

    df = pd.read_csv(INPUT_FILE)
    print(f"Loaded {len(df)} records")

    print("Fetching waitlist stats...")
    waitlist = fetch_waitlist_stats()
    if waitlist:
        print(f"  Latest quarter: {waitlist['latest'].get('Quarter', '?')}")

    buildings = prepare_buildings(df)
    html = build_html(buildings, waitlist)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Saved: {OUTPUT_FILE}")
    print("Open in a browser to explore.")


# ── HTML template ─────────────────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Toronto Subsidized Housing</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css">
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{display:flex;height:100vh;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:13px;color:#111}

/* ── Sidebar ── */
#sidebar{width:288px;min-width:288px;display:flex;flex-direction:column;background:#fff;border-right:1px solid #e5e7eb;overflow:hidden}
#sb-head{padding:14px 16px 12px;border-bottom:1px solid #e5e7eb}
#sb-head h1{font-size:14px;font-weight:700;margin-bottom:3px}
#result-count{font-size:12px;color:#6b7280}
#filter-scroll{flex:1;overflow-y:auto;padding:14px 14px 0}

.fs{margin-bottom:14px}
.fs h3{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#9ca3af;margin-bottom:7px}

/* chips */
.chips{display:flex;flex-wrap:wrap;gap:5px}
.chip input{display:none}
.chip label{display:inline-block;padding:3px 9px;border:1px solid #d1d5db;border-radius:12px;font-size:11px;color:#4b5563;cursor:pointer;user-select:none;line-height:1.6;white-space:nowrap}
/* tooltip anchor — actual tooltip div is appended to body by JS */
[data-tip]{cursor:help}
#tip{position:fixed;z-index:9999;background:#1f2937;color:#fff;padding:5px 9px;border-radius:5px;font-size:11px;line-height:1.5;max-width:210px;word-wrap:break-word;pointer-events:none;display:none}
.chip input:checked+label{background:#1a56a0;border-color:#1a56a0;color:#fff}

/* ward list */
#ward-list{max-height:130px;overflow-y:auto;display:flex;flex-direction:column;gap:1px}
.ward-row{display:flex;align-items:center;gap:7px;padding:3px 4px;border-radius:4px;cursor:pointer}
.ward-row:hover{background:#f9fafb}
.ward-row input{accent-color:#1a56a0;cursor:pointer;flex-shrink:0}
.ward-row label{font-size:12px;color:#374151;cursor:pointer;line-height:1.4}
.ward-row label span{color:#9ca3af;font-size:11px}

/* toggles */
.tog-row{display:flex;align-items:center;justify-content:space-between;padding:4px 2px}
.tog-label{color:#374151;font-size:12px;flex:1;padding-right:8px;line-height:1.3}
.tog{position:relative;width:34px;height:18px;flex-shrink:0}
.tog input{display:none}
.tog-sl{position:absolute;inset:0;background:#d1d5db;border-radius:18px;cursor:pointer;transition:background .15s}
.tog-sl::after{content:'';position:absolute;width:12px;height:12px;background:#fff;border-radius:50%;top:3px;left:3px;transition:transform .15s}
.tog input:checked+.tog-sl{background:#1a56a0}
.tog input:checked+.tog-sl::after{transform:translateX(16px)}

hr.div{border:none;border-top:1px solid #f3f4f6;margin:4px 0 14px}
select{width:100%;padding:6px 8px;border:1px solid #d1d5db;border-radius:6px;font-size:12px;color:#374151;background:#fff}

#sb-foot{padding:12px 14px;border-top:1px solid #e5e7eb;display:flex;flex-direction:column;gap:7px}
#reset-btn{padding:7px;background:#fff;border:1px solid #d1d5db;border-radius:6px;font-size:12px;color:#374151;cursor:pointer}
#reset-btn:hover{background:#f9fafb}
#apply-btn{display:block;padding:8px;background:#1a56a0;border:none;border-radius:6px;font-size:13px;font-weight:600;color:#fff;text-align:center;text-decoration:none}
#apply-btn:hover{background:#154070}
/* availability banner */
/* listings panel */
#avail-panel{display:none;margin:10px 14px 0;border:1px solid #d1d5db;border-radius:7px;overflow:hidden}
#avail-panel.active{border-color:#bbf7d0}
.avail-head{background:#6b7280;color:#fff;padding:7px 11px;font-size:12px;font-weight:700;display:flex;align-items:center;gap:6px}
.avail-head.active{background:#16a34a}
.avail-head span{background:rgba(255,255,255,.25);border-radius:10px;padding:1px 7px;font-size:11px}
.avail-card{padding:9px 11px;background:#f0fdf4;border-top:1px solid #bbf7d0}
.avail-addr{font-size:12px;font-weight:700;color:#14532d;margin-bottom:3px}
.avail-units{font-size:11px;color:#166534;margin-bottom:3px}
.avail-eoi{font-size:11px;color:#6b7280;margin-bottom:6px}
.avail-actions{display:flex;gap:6px}
.avail-actions button,.avail-actions a{padding:4px 9px;border-radius:4px;font-size:11px;font-weight:600;cursor:pointer;text-decoration:none}
.btn-show{background:#16a34a;color:#fff;border:none}
.btn-show:hover{background:#15803d}
.btn-view{background:#fff;color:#16a34a;border:1px solid #86efac}
.btn-view:hover{background:#f0fdf4}
.avail-empty{padding:9px 11px;background:#f9fafb;border-top:1px solid #e5e7eb;font-size:12px;color:#6b7280;line-height:1.6}
.avail-empty a{color:#1a56a0;font-weight:600;text-decoration:none;cursor:pointer}
.avail-empty a:hover{text-decoration:underline}
/* subscribe */
#sub-section{border-top:1px solid #e5e7eb;padding:9px 11px 11px;background:#f9fafb}
#sub-label{font-size:11px;font-weight:600;color:#6b7280;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px}
#sub-row{display:flex;gap:6px}
#sub-email{flex:1;padding:6px 8px;border:1px solid #d1d5db;border-radius:5px;font-size:12px;min-width:0}
#sub-email:focus{outline:none;border-color:#1a56a0}
#sub-btn{padding:6px 10px;background:#1a56a0;color:#fff;border:none;border-radius:5px;font-size:12px;cursor:pointer;white-space:nowrap}
#sub-btn:hover{background:#154070}
#sub-msg{font-size:11px;margin-top:5px;min-height:16px}

/* ── Map ── */
#map-wrap{flex:1;position:relative;overflow:hidden}
#map{width:100%;height:100%}

/* ── Waitlist panel ── */
#wl-panel{position:absolute;top:12px;right:10px;z-index:1000;background:#fff;padding:11px 14px;border-radius:8px;box-shadow:0 1px 6px rgba(0,0,0,.18);min-width:205px;display:none}
#wl-panel strong{font-size:13px}
#wl-quarter{font-size:11px;color:#9ca3af;margin:2px 0 8px}
.wl-row{display:flex;justify-content:space-between;align-items:baseline;padding:2px 0}
.wl-label{font-size:11px;color:#555}
.wl-val{font-size:13px;font-weight:700}
.up{color:#c0392b}.dn{color:#27ae60}.flat{color:#bbb}
#wl-note{font-size:10px;color:#bbb;margin-top:8px}

/* ── Popup ── */
.popup-inner{max-height:290px;overflow-y:auto;padding-right:2px}
.popup-table{border-collapse:collapse;width:100%;min-width:210px}
.popup-table td{padding:2px 0;font-size:12px;vertical-align:top;line-height:1.4}
.popup-table td:first-child{color:#888;font-size:11px;padding-right:10px;white-space:nowrap;width:38%}
.popup-apply{margin-top:10px;display:flex;flex-direction:column;gap:6px}
.popup-apply a{display:grid;grid-template-columns:1fr auto;align-items:start;gap:4px;padding:9px 11px;text-decoration:none;border-radius:6px;border:1.5px solid transparent;line-height:1.3;transition:filter .15s}
.popup-apply a:hover{filter:brightness(0.93)}
.btn-label{font-size:12px;font-weight:700;display:flex;align-items:center;gap:5px}
.btn-label .ext-arrow{font-size:11px;opacity:.7}
.btn-desc{font-size:11px;font-weight:400;margin-top:2px;opacity:.85;line-height:1.4;grid-column:1/-1}
.btn-badge{font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px;white-space:nowrap;align-self:start}

/* RGI — blue, waitlist applies */
.btn-rgi{background:#dbeafe;border-color:#93c5fd;color:#1e3a5f}
.btn-rgi .btn-badge{background:#1d4ed8;color:#fff}

/* COHB — green, apply now */
.btn-cohb{background:#dcfce7;border-color:#86efac;color:#14532d}
.btn-cohb .btn-badge{background:#16a34a;color:#fff}

/* TCHC — amber, available now */
.btn-tchc{background:#fef9c3;border-color:#fde047;color:#713f12}
.btn-tchc .btn-badge{background:#ca8a04;color:#fff}
</style>
</head>
<body>

<div id="sidebar">
  <div id="sb-head">
    <h1>Toronto Subsidized Housing</h1>
    <div id="result-count">Loading...</div>
  </div>

  <div id="avail-panel">
    <div class="avail-head" id="avail-head">&#9679; TCHC Listings</div>
    <div id="avail-cards"></div>
    <div id="sub-section">
      <div id="sub-label">Get TCHC alerts</div>
      <div id="sub-row">
        <input type="email" id="sub-email" placeholder="your@email.com" onkeydown="if(event.key==='Enter')subscribe()">
        <button id="sub-btn" onclick="subscribe()">Notify me</button>
      </div>
      <div id="sub-msg"></div>
    </div>
  </div>

  <div id="filter-scroll">

    <div class="fs">
      <h3>Bedroom Size <small style="font-size:10px;color:#bbb;text-transform:none;letter-spacing:0">(any match)</small></h3>
      <div class="chips">
        <div class="chip"><input type="checkbox" id="bd_bach" data-field="Bachelor"><label for="bd_bach">Bachelor</label></div>
        <div class="chip"><input type="checkbox" id="bd_1"    data-field="One Bedroom"><label for="bd_1">1 Bed</label></div>
        <div class="chip"><input type="checkbox" id="bd_2"    data-field="Two Bedroom"><label for="bd_2">2 Bed</label></div>
        <div class="chip"><input type="checkbox" id="bd_3"    data-field="Three Bedroom"><label for="bd_3">3 Bed</label></div>
        <div class="chip"><input type="checkbox" id="bd_4"    data-field="Four Bedroom"><label for="bd_4">4 Bed</label></div>
        <div class="chip"><input type="checkbox" id="bd_5"    data-field="Five Bedroom"><label for="bd_5">5+ Bed</label></div>
      </div>
    </div>

    <div class="fs">
      <h3>Provider</h3>
      <div class="chips" id="provider-chips"></div>
    </div>

    <div class="fs">
      <h3>Building Type</h3>
      <div class="chips" id="btype-chips"></div>
    </div>

    <div class="fs">
      <h3>Ward</h3>
      <div id="ward-list"></div>
    </div>

    <hr class="div">

    <div class="fs">
      <h3>Profile</h3>
      <div class="tog-row"><span class="tog-label">Senior Building (59+)</span>
        <label class="tog"><input type="checkbox" id="tog_senior"><span class="tog-sl"></span></label></div>
      <div class="tog-row"><span class="tog-label">Smoke Free</span>
        <label class="tog"><input type="checkbox" id="tog_smoke"><span class="tog-sl"></span></label></div>
      <div class="tog-row"><span class="tog-label">Accepts Terminally Ill</span>
        <label class="tog"><input type="checkbox" id="tog_ill"><span class="tog-sl"></span></label></div>
    </div>

    <div class="fs">
      <h3>Accessibility</h3>
      <div class="tog-row"><span class="tog-label">Wheelchair Accessible Building</span>
        <label class="tog"><input type="checkbox" id="tog_wcb"><span class="tog-sl"></span></label></div>
      <div class="tog-row"><span class="tog-label">Wheelchair Accessible Units</span>
        <label class="tog"><input type="checkbox" id="tog_wcu"><span class="tog-sl"></span></label></div>
      <div class="tog-row"><span class="tog-label">Elevators</span>
        <label class="tog"><input type="checkbox" id="tog_elev"><span class="tog-sl"></span></label></div>
      <div class="tog-row"><span class="tog-label">Modified Unit Available</span>
        <label class="tog"><input type="checkbox" id="tog_mod"><span class="tog-sl"></span></label></div>
    </div>

    <div class="fs">
      <h3>Amenities</h3>
      <div class="tog-row"><span class="tog-label">Air Conditioning</span>
        <label class="tog"><input type="checkbox" id="tog_ac"><span class="tog-sl"></span></label></div>
      <div class="tog-row"><span class="tog-label">Parking</span>
        <label class="tog"><input type="checkbox" id="tog_park"><span class="tog-sl"></span></label></div>
      <div class="tog-row"><span class="tog-label">Balcony</span>
        <label class="tog"><input type="checkbox" id="tog_balc"><span class="tog-sl"></span></label></div>
      <div class="tog-row"><span class="tog-label">Hydro Included</span>
        <label class="tog"><input type="checkbox" id="tog_hydro"><span class="tog-sl"></span></label></div>
    </div>

    <div class="fs">
      <h3>Building Mandate</h3>
      <select id="mandate-sel">
        <option value="">All buildings</option>
      </select>
    </div>

    <div style="height:14px"></div>
  </div>

  <div id="sb-foot">
    <button id="reset-btn" onclick="resetFilters()">Reset all filters</button>
    <a id="apply-btn" href="#" target="_blank">Apply for Housing &#8599;</a>
  </div>


</div>

<div id="map-wrap">
  <div id="map"></div>
  <div id="wl-panel">
    <strong>City-Wide Waitlist</strong>
    <div id="wl-quarter"></div>
    <div class="wl-row"><span class="wl-label">On RGI waitlist</span><span class="wl-val" id="wl-rgi"></span></div>
    <div class="wl-row"><span class="wl-label">Affordable units</span><span class="wl-val" id="wl-aff"></span></div>
    <div id="wl-note">&#9650; increased &nbsp; &#9660; decreased vs prev quarter</div>
  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<script>
const BUILDINGS = __BUILDINGS__;
const WAITLIST  = __WAITLIST__;
const OPTIONS   = __OPTIONS__;
const APPLY_URL        = __APPLY_URL__;
const COHB_URL         = __COHB_URL__;
const TCHC_AFFORDABLE  = __TCHC_AFFORDABLE_URL__;

// ── Map ───────────────────────────────────────────────────────────────────────
let map, cluster;
const allMarkers = []; // { marker, data }

function initMap() {
  map = L.map('map').setView([43.7001, -79.4163], 12);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; OpenStreetMap &copy; CARTO',
    subdomains: 'abcd', maxZoom: 19,
  }).addTo(map);

  cluster = L.markerClusterGroup({ maxClusterRadius: 40, disableClusteringAtZoom: 15 });
  map.addLayer(cluster);

  BUILDINGS.forEach(b => {
    if (!b.lat || !b.lon) return;
    const m = L.marker([+b.lat, +b.lon]);
    m.bindPopup(buildPopup(b), { maxWidth: 320 });
    m.bindTooltip(x(b['Building Complex Name'] || b['Building Address'] || ''));
    allMarkers.push({ marker: m, data: b });
    cluster.addLayer(m);
  });

  updateCount(allMarkers.length);
  document.getElementById('apply-btn').href = APPLY_URL;
}

// ── Filters ───────────────────────────────────────────────────────────────────
const PROVIDER_TIPS = {
  'CO-OP': 'Housing co-operative — resident-run housing where members pay housing charges instead of rent and share in governance',
  'PNP':   'Private Non-Profit — housing owned and managed by a non-profit organization, often with a specific community or mandate focus',
  'TCHC':  'Toronto Community Housing Corporation — city-owned social housing, the largest provider in Toronto with ~58,000 homes',
};

function initFilters() {
  // Provider chips
  const pc = document.getElementById('provider-chips');
  OPTIONS.providerTypes.forEach(p => {
    const id  = 'pv_' + p;
    const tip = PROVIDER_TIPS[p] || '';
    pc.insertAdjacentHTML('beforeend',
      `<div class="chip"><input type="checkbox" id="${id}" data-ptype="${x(p)}"><label for="${id}" ${tip ? `data-tip="${x(tip)}"` : ''}>${x(p)}</label></div>`);
  });

  // Building type chips
  const bc = document.getElementById('btype-chips');
  OPTIONS.buildingTypes.forEach(t => {
    const id = 'bt_' + t.replace(/[^a-z0-9]/gi, '_');
    bc.insertAdjacentHTML('beforeend',
      `<div class="chip"><input type="checkbox" id="${id}" data-btype="${x(t)}"><label for="${id}">${x(t)}</label></div>`);
  });

  // Ward list
  const wl = document.getElementById('ward-list');
  OPTIONS.wards.forEach(w => {
    const name = (OPTIONS.wardNames && OPTIONS.wardNames[w]) || '';
    const id = 'wd_' + w;
    wl.insertAdjacentHTML('beforeend',
      `<div class="ward-row">
        <input type="checkbox" id="${id}" data-ward="${w}">
        <label for="${id}">Ward ${w} <span>${x(name)}</span></label>
      </div>`);
  });

  // Mandate dropdown
  const ms = document.getElementById('mandate-sel');
  OPTIONS.mandates.forEach(m => {
    const opt = document.createElement('option');
    opt.value = m; opt.textContent = m;
    ms.appendChild(opt);
  });

  document.getElementById('filter-scroll').addEventListener('change', applyFilters);
}

function getFilters() {
  return {
    bedrooms:      qAll('[data-field]').filter(e=>e.checked).map(e=>e.dataset.field),
    providers:     qAll('[data-ptype]').filter(e=>e.checked).map(e=>e.dataset.ptype),
    wards:         qAll('[data-ward]').filter(e=>e.checked).map(e=>e.dataset.ward),
    buildingTypes: qAll('[data-btype]').filter(e=>e.checked).map(e=>e.dataset.btype),
    senior: g('tog_senior').checked,
    smoke:  g('tog_smoke').checked,
    ill:    g('tog_ill').checked,
    wcb:    g('tog_wcb').checked,
    wcu:    g('tog_wcu').checked,
    elev:   g('tog_elev').checked,
    mod:    g('tog_mod').checked,
    ac:     g('tog_ac').checked,
    park:   g('tog_park').checked,
    balc:   g('tog_balc').checked,
    hydro:  g('tog_hydro').checked,
    mandate: g('mandate-sel').value,
  };
}

function matchesFilters(b, f) {
  if (f.bedrooms.length && !f.bedrooms.some(fld => b[fld] === 'Yes')) return false;
  if (f.providers.length && !f.providers.includes(b['Provider Type'])) return false;
  if (f.wards.length && !f.wards.includes(b['Ward'])) return false;
  if (f.buildingTypes.length) {
    const bts = (b['Building Type'] || '').split('|').map(s=>s.trim());
    if (!f.buildingTypes.some(t => bts.includes(t))) return false;
  }
  if (f.senior && b['Senior Building']               !== 'Yes') return false;
  if (f.smoke  && b['Smoke Free']                    !== 'Yes') return false;
  if (f.ill    && b['Terminally Ill']                !== 'Yes') return false;
  if (f.wcb    && b['Wheelchair Accessible Building'] !== 'Yes') return false;
  if (f.wcu    && b['Wheelchair Accessible Units']    !== 'Yes') return false;
  if (f.elev   && b['Elevators']                     !== 'Yes') return false;
  if (f.mod    && b['Modified Unit']                 !== 'Yes') return false;
  if (f.ac     && b['Air Conditioning']              !== 'Yes') return false;
  if (f.park   && b['Parking']                       !== 'Yes') return false;
  if (f.balc   && b['Balcony']                       !== 'Yes') return false;
  if (f.hydro  && b['Hydro Included']                !== 'Yes') return false;
  if (f.mandate) {
    const m1 = (b['Building Mandate1'] || '').trim();
    const m2 = (b['Building Mandate2'] || '').trim();
    if (m1 !== f.mandate && m2 !== f.mandate) return false;
  }
  return true;
}

function applyFilters() {
  const f = getFilters();
  cluster.clearLayers();
  let count = 0;
  allMarkers.forEach(({marker, data}) => {
    if (matchesFilters(data, f)) { cluster.addLayer(marker); count++; }
  });
  updateCount(count);
}

function resetFilters() {
  qAll('#filter-scroll input[type=checkbox]').forEach(e => e.checked = false);
  g('mandate-sel').value = '';
  cluster.clearLayers();
  allMarkers.forEach(({marker}) => cluster.addLayer(marker));
  updateCount(allMarkers.length);
}

function updateCount(n) {
  g('result-count').textContent = n.toLocaleString() + ' of ' + allMarkers.length.toLocaleString() + ' buildings';
}

// ── Popup ─────────────────────────────────────────────────────────────────────
const BED_FIELDS = ['Bachelor','One Bedroom','Two Bedroom','Three Bedroom','Four Bedroom','Five Bedroom','Six Bedroom'];
const BED_LABELS = {'Bachelor':'Bach','One Bedroom':'1 Bed','Two Bedroom':'2 Bed','Three Bedroom':'3 Bed',
                    'Four Bedroom':'4 Bed','Five Bedroom':'5 Bed','Six Bedroom':'6 Bed'};
const INFO_FIELDS = [
  ['Building Complex Name','Name'],['Building Address','Address'],
  ['Ward','Ward'],['Building Postal Code','Postal Code'],
  ['Provider Name','Provider'],['Provider Type','Type'],
  ['Provider Website','Website'],['Building Type','Building'],
  ['Building Mandate1','Mandate'],['Building Mandate2','Mandate 2'],
];
const FEAT_FIELDS = [
  'Senior Building','Wheelchair Accessible Building','Wheelchair Accessible Units',
  'Elevators','Modified Unit','Air Conditioning','Parking','Balcony',
  'Communal Balcony','Hydro Included','Smoke Free','Terminally Ill',
];

function buildPopup(b) {
  let rows = '';

  // Bedroom availability as one compact row
  const beds = BED_FIELDS.filter(f => b[f] === 'Yes').map(f => BED_LABELS[f]);
  if (beds.length) rows += row('Available', beds.join(', '));

  // Core info
  INFO_FIELDS.forEach(([field, label]) => {
    const val = b[field];
    if (!val || String(val).trim() === '') return;
    if (field === 'Provider Website')
      rows += row(label, `<a href="${x(val)}" target="_blank">${x(val)}</a>`);
    else if (field === 'Ward')
      rows += row(label, x(val) + (OPTIONS.wardNames[val] ? ' — ' + x(OPTIONS.wardNames[val]) : ''));
    else
      rows += row(label, x(String(val)));
  });

  // Features: only show Yes ones as a compact line
  const feats = FEAT_FIELDS.filter(f => b[f] === 'Yes').map(f => x(f));
  if (feats.length) rows += row('Features', feats.join(' &middot; '));

  const isTCHC = b['Provider Type'] === 'TCHC';

  const applyBtns = `
    <a href="${x(APPLY_URL)}" target="_blank" class="btn-rgi">
      <span class="btn-label">Apply for Subsidized Housing <span class="ext-arrow">&#8599;</span></span>
      <span class="btn-badge">Waitlist</span>
      <span class="btn-desc">Rent-Geared-to-Income (RGI) — pay ~30% of your income. Waitlist is years long but most affordable option.</span>
    </a>
    <a href="${x(COHB_URL)}" target="_blank" class="btn-cohb">
      <span class="btn-label">Canada-Ontario Housing Benefit <span class="ext-arrow">&#8599;</span></span>
      <span class="btn-badge">Apply now</span>
      <span class="btn-desc">Monthly top-up of up to $500 toward rent in your current or new home. No waitlist — apply directly.</span>
    </a>
    ${isTCHC ? `<a href="${x(TCHC_AFFORDABLE)}" target="_blank" class="btn-tchc">
      <span class="btn-label">TCHC Unit Listings <span class="ext-arrow">&#8599;</span></span>
      <span class="btn-badge">Check listings</span>
      <span class="btn-desc">This building is TCHC-owned. Check for open Expressions of Interest — TCHC posts units here as they become available.</span>
    </a>` : ''}
  `;

  return `<div class="popup-inner"><table class="popup-table">${rows}</table></div>
<div class="popup-apply">${applyBtns}</div>`;
}

function row(label, val) {
  return `<tr><td>${label}</td><td>${val}</td></tr>`;
}

// ── Waitlist panel ─────────────────────────────────────────────────────────────
function initWaitlist() {
  if (!WAITLIST) return;
  const l = WAITLIST.latest, p = WAITLIST.previous || {};

  function trend(a, b) {
    const parse = v => parseInt(String(v||'').replace(/,/g,''));
    const va = parse(a), vb = parse(b);
    if (isNaN(va)||isNaN(vb)) return '';
    return va > vb ? ' <span class="up">&#9650;</span>'
         : va < vb ? ' <span class="dn">&#9660;</span>'
         : ' <span class="flat">&#9644;</span>';
  }

  g('wl-quarter').textContent = (l['Quarter']||'') + ' — refreshed quarterly';
  g('wl-rgi').innerHTML = x(l['Subsidized Housing Units']||'n/a') + trend(l['Subsidized Housing Units'], p['Subsidized Housing Units']);
  g('wl-aff').innerHTML = x(l['Affordable Housing Units']||'n/a') + trend(l['Affordable Housing Units'], p['Affordable Housing Units']);
  g('wl-panel').style.display = 'block';
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function g(id) { return document.getElementById(id); }
function qAll(sel) { return [...document.querySelectorAll(sel)]; }
function x(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

// ── Tooltip (body-level, escapes overflow:hidden containers) ──────────────────
function initTooltips() {
  const tip = document.createElement('div');
  tip.id = 'tip';
  document.body.appendChild(tip);

  function position(e) {
    const pad = 10, w = tip.offsetWidth, h = tip.offsetHeight;
    let top  = e.clientY - h - pad;
    let left = e.clientX - w / 2;
    if (top  < pad) top = e.clientY + pad;          // flip below cursor if too high
    if (left < pad) left = pad;
    if (left + w > window.innerWidth  - pad) left = window.innerWidth  - w - pad;
    if (top  + h > window.innerHeight - pad) top  = window.innerHeight - h - pad;
    tip.style.left = left + 'px';
    tip.style.top  = top  + 'px';
  }

  document.querySelectorAll('[data-tip]').forEach(el => {
    el.addEventListener('mouseenter', e => { tip.textContent = el.dataset.tip; tip.style.display = 'block'; position(e); });
    el.addEventListener('mousemove',  e => position(e));
    el.addEventListener('mouseleave', () => { tip.style.display = 'none'; });
  });
}

// ── Listings availability ─────────────────────────────────────────────────────
// Green marker icon for buildings with active listings
const availIcon = L.divIcon({
  className: '',
  html: '<div style="width:22px;height:22px;background:#16a34a;border:2.5px solid #fff;border-radius:50%;box-shadow:0 1px 6px rgba(0,0,0,.35)"></div>',
  iconSize: [22, 22], iconAnchor: [11, 11], popupAnchor: [0, -13],
});

function findMarkerByAddress(hint) {
  if (!hint) return null;
  const h    = hint.toLowerCase().trim();
  const numM = h.match(/^(\\d+)/);
  const num  = numM ? numM[1] : null;
  // Street type abbreviations to normalise
  const norm = s => s.replace(/\\bave\\.?\\b/g,'ave').replace(/\\bst\\.?\\b/g,'st').replace(/\\brd\\.?\\b/g,'rd').replace(/\\bblvd\\.?\\b/g,'blvd');

  return allMarkers.find(({data}) => {
    const addr = norm((data['Building Address'] || '').toLowerCase());
    if (num && !addr.includes(num)) return false;
    const words = norm(h).split(/\\s+/).filter(w => w.length > 2 && isNaN(w));
    return words.some(w => addr.includes(w));
  }) || null;
}

function showOnMap(markerObj) {
  if (!markerObj) return;
  cluster.zoomToShowLayer(markerObj.marker, () => {
    markerObj.marker.openPopup();
  });
}

function checkListings() {
  const panel = g('avail-panel');
  const head  = g('avail-head');
  const cards = g('avail-cards');

  fetch('/api/listings')
    .then(r => r.ok ? r.json() : null)
    .then(data => {
      panel.style.display = 'block';

      if (!data || !data.has_listings || !data.listings?.length) {
        // No active listings — show empty state
        panel.classList.remove('active');
        head.classList.remove('active');
        head.innerHTML = '&#9675; TCHC Listings';
        cards.innerHTML = `<div class="avail-empty">
          No units available right now.<br>
          <a href="#" onclick="event.preventDefault();g('sub-email').focus()">Sign up for alerts</a>
          and we'll email you when units open.
        </div>`;
        return;
      }

      // Active listings — green header + cards
      panel.classList.add('active');
      head.classList.add('active');

      const listing_cards = data.listings.map((l, i) => {
        const matched = findMarkerByAddress(l.address);
        if (matched) matched.marker.setIcon(availIcon);

        const units = (l.units || []).map(u => `${u.count}×${u.type}`).join(' &nbsp;·&nbsp; ');
        const showBtn = matched
          ? `<button class="btn-show" onclick="showOnMap(window._availMarkers[${i}])">Show on map</button>`
          : '';

        if (matched) {
          window._availMarkers = window._availMarkers || [];
          window._availMarkers[i] = matched;
        }

        return `<div class="avail-card">
          <div class="avail-addr">${x(l.address)}</div>
          ${units ? `<div class="avail-units">${units}</div>` : ''}
          ${l.eoi  ? `<div class="avail-eoi">${x(l.eoi)}</div>` : ''}
          <div class="avail-actions">
            ${showBtn}
            <a class="btn-view" href="https://torontohousing.ca/prospective-tenants/affordable-rent" target="_blank">View listing &#8599;</a>
          </div>
        </div>`;
      });

      const n = data.listings.length;
      head.innerHTML = `&#9679; Available Now <span>${n === 1 ? '1 listing' : n + ' listings'}</span>`;
      cards.innerHTML = listing_cards.join('');
    })
    .catch(() => {});  // silently skip if not running via server.py
}

// ── Subscribe ─────────────────────────────────────────────────────────────────
function subscribe() {
  const email = g('sub-email').value.trim();
  const msg   = g('sub-msg');
  if (!email) { msg.style.color = '#dc2626'; msg.textContent = 'Enter your email.'; return; }

  g('sub-btn').disabled = true;
  fetch('/api/subscribe', {
    method:  'POST',
    headers: {'Content-Type': 'application/json'},
    body:    JSON.stringify({email}),
  })
  .then(r => r.json())
  .then(d => {
    if (d.ok) {
      g('sub-row').style.display = 'none';
      msg.style.color = '#166534';
      msg.textContent = '✓ ' + d.message;
    } else {
      msg.style.color = '#dc2626';
      msg.textContent = d.error || 'Could not subscribe.';
      g('sub-btn').disabled = false;
    }
  })
  .catch(() => {
    msg.style.color = '#dc2626';
    msg.textContent = 'Server not running — start server.py first.';
    g('sub-btn').disabled = false;
  });
}

// ── Boot ──────────────────────────────────────────────────────────────────────
initMap();
initFilters();
initWaitlist();
initTooltips();
checkListings();
</script>
</body>
</html>"""


if __name__ == "__main__":
    run()
