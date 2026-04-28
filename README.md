# 🗺 Smart Route Finder

> A production-grade, full-stack navigation system built with Python, Flask, OSMnx, and Folium — comparable in architecture to Google Maps.

> Live at: https://smart-route-finder-n52n.onrender.com/
---

## 📁 Project Structure

```
smart_route_optimizer/
├── app.py                      # Flask application (entry point)
├── requirements.txt
│
├── routing/
│   ├── algorithms.py           # Dijkstra & A* implementations
│   ├── graph_manager.py        # OSMnx graph download & caching
│   ├── demo_graph.py           # Synthetic city graph (offline fallback)
│   └── route_service.py        # High-level routing orchestrator
│
├── utils/
│   ├── helpers.py              # Geocoding, fare calc, weather, history
│   └── map_renderer.py         # Folium multi-route map builder
│
├── api/
│   └── traffic.py              # OpenRouteService + synthetic traffic
│
├── templates/
│   ├── base.html               # Shared nav, fonts, styles
│   ├── index.html              # Home page (route input form)
│   ├── results.html            # Route comparison + metrics
│   └── map_view.html           # Full-screen map page
│
├── static/
│   ├── css/                    # Optional custom stylesheets
│   ├── js/                     # Optional custom scripts
│   └── maps/                   # Generated Folium HTML maps (auto-created)
│
└── data/
    ├── graph_cache/            # Pickled OSMnx graphs (auto-created)
    └── search_history.json     # Saved search history (auto-created)
```

---



## 🌐 Features

| Feature | Details |
|---|---|
| **Algorithms** | Dijkstra (shortest path) + A\* (fastest/optimal) |
| **Road Network** | Real OSMnx data from OpenStreetMap; synthetic fallback |
| **Three Routes** | Fastest (time), Shortest (distance), Optimal (balanced) |
| **Fare Estimate** | Base + distance + time + surge pricing |
| **Traffic** | OpenRouteService API or synthetic rush-hour simulation |
| **Weather** | 6 conditions — speed factor applied to ETA |
| **GPS** | Browser geolocation → reverse geocoded starting point |
| **Map** | Folium interactive map with multi-route overlays + legend |
| **History** | Last 20 searches persisted to JSON |
| **Recommendation** | Weighted scoring across time, distance, fare |

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Home page with route form |
| `POST` | `/route` | Find & compare routes |
| `GET` | `/geocode?address=...` | Geocode an address to coordinates |
| `GET` | `/reverse-geocode?lat=&lon=` | Coordinates → address |
| `GET` | `/history` | JSON list of recent searches |
| `GET` | `/health` | Service health check |
| `GET` | `/map/<session_id>` | Full-screen map viewer |

---

## 🧪 Sample Inputs & Outputs

### Input

| Field | Example |
|---|---|
| Origin | `Connaught Place, Delhi` |
| Destination | `India Gate` |
| Weather | Rain |
| Traffic | Enabled |

### Output

```
Fastest Route  (A*)       — 3.97 km | 5.7 min  | $8.69
Shortest Route (Dijkstra) — 3.76 km | 6.2 min  | $8.14
Optimal Route  (A*)       — 3.97 km | 5.1 min  | $8.36
Recommended:   Optimal
Traffic:       Light traffic (×1.0 delay)
Weather:       🌧️ Rain (speed ×0.75)
```

Other working location pairs:
- `Mumbai` → `Pune` (requires OSM network or enter coordinates)
- `London` → `28.61, 77.22` (mix of city name + coordinates)
- `51.5074, -0.1278` → `51.52, -0.09` (raw coordinates)

---

## 🏗 Architecture

```
Browser
  │
  ▼
Flask (app.py)
  │
  ├── /route POST
  │     └── RouteService.find_routes()
  │           ├── Geocode (Nominatim → offline fallback)
  │           ├── OSMnx graph download → cache (demo graph fallback)
  │           ├── Traffic API (ORS → synthetic)
  │           ├── A* on travel_time  → Fastest
  │           ├── Dijkstra on length → Shortest
  │           ├── A* on balanced     → Optimal
  │           ├── Fare calculation + surge logic
  │           ├── Route recommendation (weighted score)
  │           └── Folium map render → /static/maps/*.html
  │
  └── Jinja2 templates → results.html (Bootstrap + custom CSS)
```

---

## 🔧 Configuration

Edit `utils/helpers.py` to change fare parameters:

```python
BASE_FARE       = 2.50   # USD flat pickup charge
RATE_PER_KM     = 1.20   # USD per kilometre
RATE_PER_MIN    = 0.25   # USD per minute
SURGE_THRESHOLD = 15     # km above which surge kicks in
SURGE_MULTIPLIER = 1.3   # 30% surge factor
```

---

## 🗺 Offline / Demo Mode

When the OSM Overpass API is unreachable (firewall, air-gapped systems), the system automatically switches to a **synthetic 12×12 city grid** with:
- Primary arterials (60 km/h)
- Secondary roads (40 km/h)
- Residential streets (25 km/h)
- Diagonal express corridors (70 km/h)

The algorithms, metrics, fare calculation, and Folium map all work identically in demo mode.

---

## 📦 Dependencies

| Package | Purpose |
|---|---|
| `flask` | Web framework |
| `osmnx` | OpenStreetMap graph download |
| `networkx` | Graph data structure |
| `folium` | Interactive map rendering |
| `geopy` | Nominatim geocoding |
| `requests` | Traffic API calls |
| `shapely` | Geometry handling |
| `numpy`, `scipy` | Numerical utilities |

---

## 👨‍💻 Built With

- **Backend:** Python 3.10+, Flask 3.0
- **Algorithms:** Custom Dijkstra + A\* with haversine heuristic
- **Road Network:** OSMnx + OpenStreetMap
- **Maps:** Folium (Leaflet.js)
- **Traffic:** OpenRouteService API
- **Geocoding:** Nominatim (OpenStreetMap)
- **Frontend:** Jinja2, Bootstrap Icons, custom CSS (Space Grotesk + Playfair Display)
- **Design:** Dark futuristic UI with animated grid background

---

*Built by: Gaurav Gautam*
