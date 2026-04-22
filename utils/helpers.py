"""
Utility functions: geocoding, fare calculation,
weather simulation, search history persistence.
"""

import json
import os
import math
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "search_history.json")
os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)

_geolocator = Nominatim(user_agent="smart_route_optimizer_v1", timeout=10)

# ── Offline geocoding fallback ──────────────────────────────────────────────
# Used when Nominatim is unreachable (network-restricted environments)
_KNOWN_LOCATIONS = {
    # India
    "connaught place": (28.6315, 77.2167, "Connaught Place, New Delhi, India"),
    "india gate": (28.6129, 77.2295, "India Gate, New Delhi, India"),
    "new delhi": (28.6139, 77.2090, "New Delhi, India"),
    "delhi": (28.7041, 77.1025, "Delhi, India"),
    "mumbai": (19.0760, 72.8777, "Mumbai, Maharashtra, India"),
    "bangalore": (12.9716, 77.5946, "Bangalore, Karnataka, India"),
    "chennai": (13.0827, 80.2707, "Chennai, Tamil Nadu, India"),
    "hyderabad": (17.3850, 78.4867, "Hyderabad, Telangana, India"),
    "kolkata": (22.5726, 88.3639, "Kolkata, West Bengal, India"),
    "pune": (18.5204, 73.8567, "Pune, Maharashtra, India"),
    "ahmedabad": (23.0225, 72.5714, "Ahmedabad, Gujarat, India"),
    "kurnool": (15.8281, 78.0373, "Kurnool, Andhra Pradesh, India"),
    "vizag": (17.6868, 83.2185, "Visakhapatnam, Andhra Pradesh, India"),
    "visakhapatnam": (17.6868, 83.2185, "Visakhapatnam, Andhra Pradesh, India"),
    # US
    "new york": (40.7128, -74.0060, "New York City, NY, USA"),
    "los angeles": (34.0522, -118.2437, "Los Angeles, CA, USA"),
    "chicago": (41.8781, -87.6298, "Chicago, IL, USA"),
    "san francisco": (37.7749, -122.4194, "San Francisco, CA, USA"),
    "seattle": (47.6062, -122.3321, "Seattle, WA, USA"),
    # UK
    "london": (51.5074, -0.1278, "London, UK"),
    "manchester": (53.4808, -2.2426, "Manchester, UK"),
    # Other
    "paris": (48.8566, 2.3522, "Paris, France"),
    "berlin": (52.5200, 13.4050, "Berlin, Germany"),
    "tokyo": (35.6762, 139.6503, "Tokyo, Japan"),
    "sydney": (-33.8688, 151.2093, "Sydney, Australia"),
    "dubai": (25.2048, 55.2708, "Dubai, UAE"),
    "singapore": (1.3521, 103.8198, "Singapore"),
    "beijing": (39.9042, 116.4074, "Beijing, China"),
}


def _offline_geocode(address: str) -> dict:
    """
    Match address to known locations (case-insensitive substring match).
    Also supports 'lat,lon' coordinate strings.
    """
    addr_lower = address.strip().lower()

    # Try direct coordinate input: "28.6315, 77.2167"
    import re
    coord_match = re.match(r"^\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*$", address)
    if coord_match:
        lat, lon = float(coord_match.group(1)), float(coord_match.group(2))
        return {"lat": lat, "lon": lon, "display_name": f"{lat:.5f}, {lon:.5f}"}

    # Exact or substring match
    for key, (lat, lon, name) in _KNOWN_LOCATIONS.items():
        if key in addr_lower or addr_lower in key:
            return {"lat": lat, "lon": lon, "display_name": name}

    raise ValueError(
        f"Cannot geocode '{address}'. "
        "Network is unavailable and this location is not in the offline database. "
        "Try: 'Connaught Place Delhi', 'India Gate', 'Mumbai', 'New York', 'London', "
        "or enter coordinates as 'lat, lon' (e.g. '28.6315, 77.2167')."
    )


# ── Geocoding ──────────────────────────────────────────────────────────────

def geocode(address: str) -> dict:
    """
    Convert address string to {lat, lon, display_name}.
    Tries Nominatim first; falls back to offline lookup.
    Raises ValueError if both fail.
    """
    try:
        loc = _geolocator.geocode(address)
        if loc is not None:
            return {
                "lat": loc.latitude,
                "lon": loc.longitude,
                "display_name": loc.address,
            }
    except Exception:
        pass   # Network unavailable — try offline

    return _offline_geocode(address)


def reverse_geocode(lat: float, lon: float) -> str:
    """Convert (lat, lon) to human-readable address."""
    def nearest_known_location() -> str | None:
        closest_name = None
        closest_distance = float("inf")

        for known_lat, known_lon, name in _KNOWN_LOCATIONS.values():
            distance = math.hypot(lat - known_lat, lon - known_lon)
            if distance < closest_distance:
                closest_distance = distance
                closest_name = name

        # Rough threshold so we only use a known place when it is reasonably nearby.
        return closest_name if closest_distance < 0.35 else None

    try:
        loc = _geolocator.reverse((lat, lon), language='en')
        if loc:
            # Try to get display_name first (more reliable), then address
            if hasattr(loc, 'display_name') and loc.display_name:
                # Extract city/place name from display_name
                parts = loc.display_name.split(',')
                if len(parts) >= 2:
                    # Usually format: "Place, City, State, Country"
                    # Return the first 2-3 parts
                    place_name = ', '.join(p.strip() for p in parts[:2])
                    return place_name if place_name else loc.display_name
                return loc.display_name
            elif loc.address:
                parts = loc.address.split(',')
                place_name = ', '.join(p.strip() for p in parts[:2])
                return place_name if place_name else loc.address
        fallback_name = nearest_known_location()
        return fallback_name or f"{lat:.5f}, {lon:.5f}"
    except Exception:
        # Prefer a nearby known location over raw coordinates when network geocoding fails.
        fallback_name = nearest_known_location()
        return fallback_name or f"{lat:.5f}, {lon:.5f}"


def extract_city(address: str) -> str:
    """
    Best-effort extract city/region from address for graph download.
    Falls back to the full address string.
    """
    geocoded = geocode(address)
    parts = geocoded["display_name"].split(",")
    # Try to find county/city/state level (3rd or 4th from end)
    if len(parts) >= 4:
        return ", ".join(p.strip() for p in parts[-4:-1])
    return geocoded["display_name"]


# ── Vehicle Types ───────────────────────────────────────────────────────────

VEHICLE_TYPES = {
    "economy": {
        "name": "Economy",
        "emoji": "🚗",
        "base_fare": 50,
        "rate_per_km": 25,
        "rate_per_min": 5,
        "time_multiplier": 1.0,
    },
    "premium": {
        "name": "Premium",
        "emoji": "🚙",
        "base_fare": 80,
        "rate_per_km": 35,
        "rate_per_min": 7,
        "time_multiplier": 0.95,
    },
    "bike": {
        "name": "Bike",
        "emoji": "🏍️",
        "base_fare": 30,
        "rate_per_km": 18,
        "rate_per_min": 3,
        "time_multiplier": 0.8,
    },
    "auto": {
        "name": "Auto Rickshaw",
        "emoji": "🚙",
        "base_fare": 25,
        "rate_per_km": 12,
        "rate_per_min": 2,
        "time_multiplier": 1.1,
    },
}


# ── Fare Calculation ────────────────────────────────────────────────────────

BASE_FARE = 50            # INR
RATE_PER_KM = 25          # INR per km
RATE_PER_MIN = 5          # INR per min
SURGE_THRESHOLD_KM = 15   # km above which surge applies
SURGE_MULTIPLIER = 1.3


def calculate_fare(distance_km: float, time_min: float, surge: bool = False, vehicle_type: str = "economy") -> dict:
    """
    Calculate ride fare with optional surge pricing for specified vehicle type.
    Returns breakdown dict.
    """
    # Get vehicle-specific rates
    vehicle = VEHICLE_TYPES.get(vehicle_type, VEHICLE_TYPES["economy"])
    
    base = vehicle["base_fare"]
    dist_charge = distance_km * vehicle["rate_per_km"]
    time_charge = time_min * vehicle["rate_per_min"]
    subtotal = base + dist_charge + time_charge

    surge_mult = SURGE_MULTIPLIER if (surge or distance_km > SURGE_THRESHOLD_KM) else 1.0
    total = round(subtotal * surge_mult, 2)

    return {
        "base_fare": round(base, 2),
        "distance_charge": round(dist_charge, 2),
        "time_charge": round(time_charge, 2),
        "surge_multiplier": surge_mult,
        "total": total,
        "currency": "INR",
        "vehicle_type": vehicle_type,
        "vehicle_name": vehicle["name"],
    }


# ── Weather Simulation ──────────────────────────────────────────────────────

WEATHER_CONDITIONS = {
    "clear": {"label": "☀️ Clear", "speed_factor": 1.0, "color": "#f5c518"},
    "cloudy": {"label": "☁️ Cloudy", "speed_factor": 0.95, "color": "#9e9e9e"},
    "rain": {"label": "🌧️ Rain", "speed_factor": 0.75, "color": "#1565c0"},
    "heavy_rain": {"label": "⛈️ Heavy Rain", "speed_factor": 0.55, "color": "#4a148c"},
    "fog": {"label": "🌫️ Fog", "speed_factor": 0.60, "color": "#78909c"},
    "snow": {"label": "❄️ Snow", "speed_factor": 0.40, "color": "#80d8ff"},
}


def simulate_weather(condition: str = "clear") -> dict:
    """Return weather impact metadata for a given condition string."""
    return WEATHER_CONDITIONS.get(condition, WEATHER_CONDITIONS["clear"])


# ── Route Recommendation ────────────────────────────────────────────────────

def recommend_route(routes: list) -> str:
    """
    Given a list of route dicts with keys distance_km, time_min, fare,
    return the label of the recommended route using a simple score.
    Score = normalize(time) * 0.5 + normalize(distance) * 0.3 + normalize(fare) * 0.2
    Lower is better.
    """
    if not routes:
        return ""
    if len(routes) == 1:
        return routes[0]["label"]

    keys = ["time_min", "distance_km", "fare_total"]
    weights = [0.5, 0.3, 0.2]
    values = {k: [r.get(k, 0) for r in routes] for k in keys}
    maxv = {k: max(values[k]) or 1 for k in keys}
    minv = {k: min(values[k]) for k in keys}

    scores = []
    for r in routes:
        score = sum(
            w * (r.get(k, 0) - minv[k]) / (maxv[k] - minv[k] + 1e-9)
            for w, k in zip(weights, keys)
        )
        scores.append(score)

    best_idx = scores.index(min(scores))
    return routes[best_idx]["label"]


def get_city_suggestions(query: str, limit: int = 8) -> list:
    """
    Return a list of matching cities/locations from known locations.
    Searches using word-based matching across all location data.
    Returns list of dicts with proper formatting for UI display.
    """
    if not query or len(query.strip()) < 1:
        return []
    
    query_lower = query.strip().lower()
    matches = []
    
    for key, (lat, lon, display_name) in _KNOWN_LOCATIONS.items():
        # Check if query matches key or any part of display_name
        display_lower = display_name.lower()
        key_match = query_lower in key or key.startswith(query_lower)
        display_match = query_lower in display_lower or any(
            part.startswith(query_lower) for part in display_lower.split()
        )
        
        if key_match or display_match:
            # Parse display_name to extract city and region
            parts = [p.strip() for p in display_name.split(",")]
            city = parts[0] if parts else display_name
            region = parts[-2] if len(parts) > 2 else (parts[-1] if len(parts) > 1 else "")
            country = parts[-1] if len(parts) > 1 else ""
            
            # Determine emoji based on country
            emoji = "🇮🇳" if "India" in country else "🌍"
            
            matches.append({
                "name": city,
                "display_name": display_name,
                "region": region,
                "country": country,
                "emoji": emoji,
                "lat": lat,
                "lon": lon,
            })
    
    # Remove duplicates by display_name and return top matches
    seen = set()
    unique_matches = []
    for m in matches:
        if m["display_name"] not in seen:
            seen.add(m["display_name"])
            unique_matches.append(m)
    
    return unique_matches[:limit]


# ── Search History ──────────────────────────────────────────────────────────

def load_history() -> list:
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def save_to_history(origin: str, destination: str):
    history = load_history()
    entry = {"origin": origin, "destination": destination}
    # Avoid duplicates at top
    if history and history[-1] == entry:
        return
    history.append(entry)
    history = history[-20:]  # Keep last 20
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f)
