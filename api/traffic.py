"""
Traffic API integration.
Primary: OpenRouteService (free tier)
Fallback: synthetic traffic simulation
"""

import os
import math
import random
import requests
from typing import Optional


ORS_API_KEY = os.environ.get("ORS_API_KEY", "")  # Set in environment
ORS_BASE_URL = "https://api.openrouteservice.org/v2/directions/driving-car"


# ── OpenRouteService ────────────────────────────────────────────────────────

def get_ors_route(origin_lon, origin_lat, dest_lon, dest_lat) -> Optional[dict]:
    """
    Fetch route from OpenRouteService. Returns parsed summary or None.
    """
    if not ORS_API_KEY:
        return None

    headers = {"Authorization": ORS_API_KEY, "Content-Type": "application/json"}
    body = {
        "coordinates": [[origin_lon, origin_lat], [dest_lon, dest_lat]],
        "instructions": False,
    }
    try:
        resp = requests.post(ORS_BASE_URL, json=body, headers=headers, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        summary = data["routes"][0]["summary"]
        geometry = data["routes"][0]["geometry"]
        return {
            "distance_km": round(summary["distance"] / 1000, 2),
            "time_min": round(summary["duration"] / 60, 1),
            "geometry": geometry,
        }
    except Exception:
        return None


def get_traffic_multiplier_ors(origin_lon, origin_lat, dest_lon, dest_lat) -> float:
    """
    Compare ORS duration vs free-flow estimate to derive traffic multiplier.
    Returns 1.0 if ORS unavailable.
    """
    result = get_ors_route(origin_lon, origin_lat, dest_lon, dest_lat)
    if not result:
        return _synthetic_traffic_multiplier(origin_lat, origin_lon)

    dist_km = result["distance_km"]
    actual_min = result["time_min"]
    free_flow_min = (dist_km / 50.0) * 60.0  # 50 km/h free flow

    if free_flow_min < 0.1:
        return 1.0
    return round(actual_min / free_flow_min, 2)


# ── Synthetic Traffic (fallback) ────────────────────────────────────────────

def _synthetic_traffic_multiplier(lat: float, lon: float) -> float:
    """
    Deterministic pseudo-random traffic based on location hash.
    Simulates rush-hour patterns realistically.
    """
    import datetime
    hour = datetime.datetime.now().hour
    # Rush hours: 7-9 AM and 5-7 PM
    if 7 <= hour <= 9 or 17 <= hour <= 19:
        base = 1.6
    elif 10 <= hour <= 16:
        base = 1.2
    else:
        base = 1.0

    # Small location-based noise
    rng = random.Random(int(abs(lat * 1000) + abs(lon * 1000)))
    noise = rng.uniform(-0.1, 0.1)
    return round(max(1.0, base + noise), 2)


def get_traffic_info(origin_lat, origin_lon, dest_lat, dest_lon) -> dict:
    """
    High-level traffic info fetch.
    Returns {multiplier, source, description}.
    """
    mult = get_traffic_multiplier_ors(origin_lon, origin_lat, dest_lon, dest_lat)

    if mult <= 1.05:
        level, color = "Light", "#4caf50"
    elif mult <= 1.3:
        level, color = "Moderate", "#ff9800"
    elif mult <= 1.6:
        level, color = "Heavy", "#f44336"
    else:
        level, color = "Severe", "#b71c1c"

    return {
        "multiplier": mult,
        "level": level,
        "color": color,
        "description": f"{level} traffic (×{mult:.1f} delay)",
        "source": "OpenRouteService" if ORS_API_KEY else "Synthetic simulation",
    }
