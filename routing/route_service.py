# """
# RouteService: orchestrates the full routing pipeline.
# Compatible with osmnx 1.x and 2.x.
# Falls back to synthetic demo graph when OSM/network is unavailable.
# """

# import math
# import uuid
# import traceback

# from routing.algorithms import astar, dijkstra, compute_path_metrics
# from routing.demo_graph import get_demo_graph
# from api.traffic import get_traffic_info
# from utils.helpers import geocode, calculate_fare, simulate_weather, recommend_route
# from utils.map_renderer import render_map


# def _haversine(lat1, lon1, lat2, lon2):
#     R = 6371.0
#     p1, p2 = math.radians(lat1), math.radians(lat2)
#     dp = math.radians(lat2 - lat1)
#     dl = math.radians(lon2 - lon1)
#     a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
#     return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# def _nearest_node_manual(G, lat, lon):
#     """Fallback nearest-node by haversine (used for demo graph)."""
#     best, best_d = None, float("inf")
#     for nid, data in G.nodes(data=True):
#         d = _haversine(lat, lon, data["y"], data["x"])
#         if d < best_d:
#             best_d = d
#             best = nid
#     return best


# def _ox_nearest_node(G, lon, lat):
#     """
#     Call osmnx nearest_nodes, compatible with v1.x and v2.x.
#     v1.x: ox.nearest_nodes(G, X, Y)   where X=lon, Y=lat
#     v2.x: same signature but may behave slightly differently
#     """
#     import osmnx as ox
#     return ox.nearest_nodes(G, lon, lat)


# def _add_balanced_weights(G, traffic_mult: float):
#     for u, v, k, data in G.edges(keys=True, data=True):
#         dist = data.get("length", 100)
#         time = data.get("travel_time", dist / 14) * traffic_mult
#         G[u][v][k]["balanced"] = 0.4 * dist + 0.6 * time * 14


# def _try_osmnx(center_lat, center_lon, radius_m):
#     """Download real OSMnx graph. Returns (G, False) or (None, True) on failure."""
#     try:
#         import osmnx as ox
#         ox.settings.log_console = False
#         G = ox.graph_from_point(
#             (center_lat, center_lon),
#             dist=radius_m,
#             network_type="drive",
#             simplify=True,
#         )
#         G = ox.add_edge_speeds(G)
#         G = ox.add_edge_travel_times(G)
#         return G, False
#     except Exception:
#         return None, True


# class RouteService:
#     def __init__(self):
#         self._cache = {}

#     def find_routes(
#         self,
#         origin_address: str,
#         dest_address: str,
#         weather_condition: str = "clear",
#         use_traffic: bool = True,
#     ) -> dict:

#         # 1. Geocode
#         origin = geocode(origin_address)
#         dest   = geocode(dest_address)

#         dist_km  = _haversine(origin["lat"], origin["lon"], dest["lat"], dest["lon"])

#         # Cap radius at 15 km to prevent massive OSM downloads.
#         # For longer trips the demo graph (synthetic) is used automatically.
#         MAX_RADIUS_M = 15000
#         raw_radius   = int(dist_km * 800)
#         radius_m     = min(max(raw_radius, 2500), MAX_RADIUS_M)
#         center_lat   = (origin["lat"] + dest["lat"]) / 2
#         center_lon   = (origin["lon"] + dest["lon"]) / 2

#         if dist_km > 18:
#             raise ValueError(
#                 f"The two locations are {dist_km:.0f} km apart — too far for live routing. "
#                 "Please use locations within the same city or within ~15 km of each other. "
#                 "Examples: 'Connaught Place Delhi' → 'India Gate', "
#                 "'Colaba Mumbai' → 'Bandra Mumbai'."
#             )

#         # 2. Load graph
#         cache_key = f"{center_lat:.3f}_{center_lon:.3f}_{radius_m}"
#         if cache_key not in self._cache:
#             G, is_demo = _try_osmnx(center_lat, center_lon, radius_m)
#             if G is None:
#                 G = get_demo_graph(center_lat, center_lon)
#                 is_demo = True
#             self._cache[cache_key] = (G, is_demo)

#         G, is_demo = self._cache[cache_key]

#         # 3. Traffic & weather
#         traffic = get_traffic_info(
#             origin["lat"], origin["lon"], dest["lat"], dest["lon"]
#         )
#         traffic_mult  = traffic["multiplier"] if use_traffic else 1.0
#         weather       = simulate_weather(weather_condition)
#         combined_mult = traffic_mult * (1.0 / max(weather["speed_factor"], 0.1))

#         # 4. Nearest nodes
#         if is_demo:
#             o_node = _nearest_node_manual(G, origin["lat"], origin["lon"])
#             d_node = _nearest_node_manual(G, dest["lat"],   dest["lon"])
#         else:
#             o_node = _ox_nearest_node(G, origin["lon"], origin["lat"])
#             d_node = _ox_nearest_node(G, dest["lon"],   dest["lat"])

#         if o_node == d_node:
#             raise ValueError(
#                 "Origin and destination map to the same road node. "
#                 "Please choose locations further apart."
#             )

#         # 5. Add balanced weights
#         _add_balanced_weights(G, traffic_mult)

#         # 6. Three routing variants
#         routes_spec = [
#             ("fastest",  lambda: astar(G,    o_node, d_node, weight="travel_time"), combined_mult),
#             ("shortest", lambda: dijkstra(G, o_node, d_node, weight="length"),       1.0),
#             ("optimal",  lambda: astar(G,    o_node, d_node, weight="balanced"),     combined_mult * 0.9),
#         ]

#         session_id    = uuid.uuid4().hex[:8]
#         route_results = []

#         for rtype, compute_fn, mult in routes_spec:
#             try:
#                 path, _ = compute_fn()
#                 if not path or len(path) < 2:
#                     continue
#                 metrics = compute_path_metrics(G, path, traffic_multiplier=mult)
#                 fare    = calculate_fare(metrics["distance_km"], metrics["time_min"])
#                 route_results.append({
#                     "route_type":     rtype,
#                     "label":          rtype.capitalize(),
#                     "distance_km":    metrics["distance_km"],
#                     "time_min":       metrics["time_min"],
#                     "fare_total":     fare["total"],
#                     "fare_breakdown": fare,
#                     "coords":         metrics["coords"],
#                     "node_count":     len(path),
#                 })
#             except Exception:
#                 traceback.print_exc()

#         if not route_results:
#             raise ValueError(
#                 "No route found between these locations. "
#                 "They may not be connected in the road network. "
#                 "Try locations within the same city."
#             )

#         recommended = recommend_route(route_results)

#         map_url = render_map(
#             origin_coords=(origin["lat"], origin["lon"]),
#             dest_coords=(dest["lat"],    dest["lon"]),
#             routes=route_results,
#             origin_name=origin_address,
#             dest_name=dest_address,
#             session_id=session_id,
#         )

#         return {
#             "origin":       origin,
#             "destination":  dest,
#             "routes":       route_results,
#             "traffic":      traffic,
#             "weather":      weather,
#             "recommended":  recommended,
#             "map_url":      map_url,
#             "session_id":   session_id,
#             "graph_source": "OpenStreetMap (live)" if not is_demo else "Synthetic demo graph",
#             "dist_km":      round(dist_km, 2),
#         }


# """
# RouteService: orchestrates the full routing pipeline.
# Supports global routing:
#   - Short trips (<= 50 km): OSMnx local graph + A*/Dijkstra
#   - Long trips (> 50 km):   OpenRouteService API with straight-line
#                              interpolation fallback for 3 route variants
# Compatible with osmnx 1.x and 2.x.
# """

# import math
# import uuid
# import traceback
# import os
# import requests

# from routing.algorithms import astar, dijkstra, compute_path_metrics
# from routing.demo_graph import get_demo_graph
# from api.traffic import get_traffic_info
# from utils.helpers import geocode, calculate_fare, simulate_weather, recommend_route
# from utils.map_renderer import render_map

# ORS_API_KEY = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6ImI4ZGM3OTNiMDNhODRiOWY5ZDI4MzE5ZjBjNjFhNWE2IiwiaCI6Im11cm11cjY0In0="
# ORS_URL = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"


# # ── Helpers ───────────────────────────────────────────────────────────────────

# def _haversine(lat1, lon1, lat2, lon2):
#     R = 6371.0
#     p1, p2 = math.radians(lat1), math.radians(lat2)
#     dp = math.radians(lat2 - lat1)
#     dl = math.radians(lon2 - lon1)
#     a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
#     return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# def _nearest_node_manual(G, lat, lon):
#     best, best_d = None, float("inf")
#     for nid, data in G.nodes(data=True):
#         d = _haversine(lat, lon, data["y"], data["x"])
#         if d < best_d:
#             best_d = d
#             best = nid
#     return best


# def _ox_nearest_node(G, lon, lat):
#     import osmnx as ox
#     return ox.nearest_nodes(G, lon, lat)


# def _add_balanced_weights(G, traffic_mult):
#     for u, v, k, data in G.edges(keys=True, data=True):
#         dist = data.get("length", 100)
#         time = data.get("travel_time", dist / 14) * traffic_mult
#         G[u][v][k]["balanced"] = 0.4 * dist + 0.6 * time * 14


# def _try_osmnx(center_lat, center_lon, radius_m):
#     try:
#         import osmnx as ox
#         ox.settings.log_console = False
#         G = ox.graph_from_point(
#             (center_lat, center_lon),
#             dist=radius_m,
#             network_type="drive",
#             simplify=True,
#         )
#         G = ox.add_edge_speeds(G)
#         G = ox.add_edge_travel_times(G)
#         return G, False
#     except Exception:
#         return None, True


# # ── Long-distance routing via ORS or interpolation ───────────────────────────

# def _interpolate_coords(lat1, lon1, lat2, lon2, n=40):
#     return [
#         (lat1 + (lat2 - lat1) * i / (n - 1),
#          lon1 + (lon2 - lon1) * i / (n - 1))
#         for i in range(n)
#     ]


# def _ors_route(olat, olon, dlat, dlon):
#     if not ORS_API_KEY:
#         return None
#     try:
#         resp = requests.post(
#             ORS_URL,
#             json={"coordinates": [[olon, olat], [dlon, dlat]]},
#             headers={"Authorization": ORS_API_KEY, "Content-Type": "application/json"},
#             timeout=10,
#         )
#         resp.raise_for_status()
#         coords = resp.json()["features"][0]["geometry"]["coordinates"]
#         return [(c[1], c[0]) for c in coords]
#     except Exception:
#         return None


# def _build_long_distance_routes(origin, dest, traffic_mult, weather_mult, dist_km):
#     olat, olon = origin["lat"], origin["lon"]
#     dlat, dlon = dest["lat"], dest["lon"]

#     base_coords = _ors_route(olat, olon, dlat, dlon)
#     source = "OpenRouteService"
#     if base_coords is None:
#         base_coords = _interpolate_coords(olat, olon, dlat, dlon, n=60)
#         source = "Estimated (straight-line)"

#     def _nudge(coords, lat_offset, lon_offset):
#         result = list(coords)
#         mid = len(result) // 2
#         result[mid] = (result[mid][0] + lat_offset, result[mid][1] + lon_offset)
#         return result

#     nudge = max(dist_km * 0.002, 0.05)

#     variants = [
#         ("fastest",  base_coords,                           traffic_mult * weather_mult),
#         ("shortest", _nudge(base_coords,  nudge,  nudge),   1.0),
#         ("optimal",  _nudge(base_coords, -nudge, -nudge),   traffic_mult * weather_mult * 0.9),
#     ]

#     speeds = {"fastest": 90.0, "shortest": 70.0, "optimal": 80.0}

#     results = []
#     for rtype, coords, mult in variants:
#         total_km = sum(
#             _haversine(coords[i][0], coords[i][1], coords[i+1][0], coords[i+1][1])
#             for i in range(len(coords) - 1)
#         )
#         speed = speeds[rtype] / mult
#         time_min = (total_km / speed) * 60

#         fare = calculate_fare(total_km, time_min)
#         results.append({
#             "route_type":     rtype,
#             "label":          rtype.capitalize(),
#             "distance_km":    round(total_km, 2),
#             "time_min":       round(time_min, 1),
#             "fare_total":     fare["total"],
#             "fare_breakdown": fare,
#             "coords":         coords,
#             "node_count":     len(coords),
#             "source":         source,
#         })

#     return results


# # ── Main RouteService ─────────────────────────────────────────────────────────

# class RouteService:
#     def __init__(self):
#         self._cache = {}

#     def find_routes(
#         self,
#         origin_address: str,
#         dest_address: str,
#         weather_condition: str = "clear",
#         use_traffic: bool = True,
#     ) -> dict:

#         # 1. Geocode
#         origin = geocode(origin_address)
#         dest   = geocode(dest_address)

#         dist_km    = _haversine(origin["lat"], origin["lon"], dest["lat"], dest["lon"])
#         is_long    = dist_km > 50
#         session_id = uuid.uuid4().hex[:8]

#         # 2. Traffic & weather
#         traffic = get_traffic_info(
#             origin["lat"], origin["lon"], dest["lat"], dest["lon"]
#         )
#         traffic_mult  = traffic["multiplier"] if use_traffic else 1.0
#         weather       = simulate_weather(weather_condition)
#         weather_mult  = 1.0 / max(weather["speed_factor"], 0.1)
#         combined_mult = traffic_mult * weather_mult

#         # ── Long-distance mode (> 50 km) ─────────────────────────────────────
#         if is_long:
#             route_results = _build_long_distance_routes(
#                 origin, dest, traffic_mult, weather_mult, dist_km
#             )
#             graph_source = "OpenRouteService API" if ORS_API_KEY else "Estimated (straight-line interpolation)"

#         # ── Short-distance mode (<= 50 km): OSMnx + A*/Dijkstra ──────────────
#         else:
#             radius_m   = min(max(int(dist_km * 800), 2500), 50000)
#             center_lat = (origin["lat"] + dest["lat"]) / 2
#             center_lon = (origin["lon"] + dest["lon"]) / 2

#             cache_key = f"{center_lat:.3f}_{center_lon:.3f}_{radius_m}"
#             if cache_key not in self._cache:
#                 G, is_demo = _try_osmnx(center_lat, center_lon, radius_m)
#                 if G is None:
#                     G = get_demo_graph(center_lat, center_lon)
#                     is_demo = True
#                 self._cache[cache_key] = (G, is_demo)

#             G, is_demo = self._cache[cache_key]
#             graph_source = "OpenStreetMap (live)" if not is_demo else "Synthetic demo graph"

#             if is_demo:
#                 o_node = _nearest_node_manual(G, origin["lat"], origin["lon"])
#                 d_node = _nearest_node_manual(G, dest["lat"],   dest["lon"])
#             else:
#                 o_node = _ox_nearest_node(G, origin["lon"], origin["lat"])
#                 d_node = _ox_nearest_node(G, dest["lon"],   dest["lat"])

#             if o_node == d_node:
#                 raise ValueError(
#                     "Origin and destination map to the same road node. "
#                     "Please choose locations further apart."
#                 )

#             _add_balanced_weights(G, traffic_mult)

#             routes_spec = [
#                 ("fastest",  lambda: astar(G,    o_node, d_node, weight="travel_time"), combined_mult),
#                 ("shortest", lambda: dijkstra(G, o_node, d_node, weight="length"),       1.0),
#                 ("optimal",  lambda: astar(G,    o_node, d_node, weight="balanced"),     combined_mult * 0.9),
#             ]

#             route_results = []
#             for rtype, compute_fn, mult in routes_spec:
#                 try:
#                     path, _ = compute_fn()
#                     if not path or len(path) < 2:
#                         continue
#                     metrics = compute_path_metrics(G, path, traffic_multiplier=mult)
#                     fare    = calculate_fare(metrics["distance_km"], metrics["time_min"])
#                     route_results.append({
#                         "route_type":     rtype,
#                         "label":          rtype.capitalize(),
#                         "distance_km":    metrics["distance_km"],
#                         "time_min":       metrics["time_min"],
#                         "fare_total":     fare["total"],
#                         "fare_breakdown": fare,
#                         "coords":         metrics["coords"],
#                         "node_count":     len(path),
#                     })
#                 except Exception:
#                     traceback.print_exc()

#         if not route_results:
#             raise ValueError(
#                 "No route could be found between these locations. "
#                 "Try being more specific, e.g. add the city name."
#             )

#         recommended = recommend_route(route_results)

#         map_url = render_map(
#             origin_coords=(origin["lat"], origin["lon"]),
#             dest_coords=(dest["lat"],    dest["lon"]),
#             routes=route_results,
#             origin_name=origin_address,
#             dest_name=dest_address,
#             session_id=session_id,
#         )

#         return {
#             "origin":       origin,
#             "destination":  dest,
#             "routes":       route_results,
#             "traffic":      traffic,
#             "weather":      weather,
#             "recommended":  recommended,
#             "map_url":      map_url,
#             "session_id":   session_id,
#             "graph_source": graph_source,
#             "dist_km":      round(dist_km, 2),
# } 
# 
#       



"""
RouteService: orchestrates the full routing pipeline.
- Short trips (<= 50 km): OSMnx local graph + A*/Dijkstra
- Long trips (> 50 km): OpenRouteService API (3 real alternative routes)
- Global geocoding via ORS API with Nominatim fallback
"""

import math
import uuid
import traceback
import os
import requests

from routing.algorithms import astar, dijkstra, compute_path_metrics
from routing.demo_graph import get_demo_graph
from api.traffic import get_traffic_info
from utils.helpers import geocode as _nominatim_geocode, calculate_fare, simulate_weather, recommend_route
from utils.map_renderer import render_map

ORS_API_KEY = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6ImI4ZGM3OTNiMDNhODRiOWY5ZDI4MzE5ZjBjNjFhNWE2IiwiaCI6Im11cm11cjY0In0="
ORS_BASE    = "https://api.openrouteservice.org"
ORS_HEADERS = {"Authorization": ORS_API_KEY, "Content-Type": "application/json"}


# ── Geocoding (ORS global + Nominatim fallback) ───────────────────────────────

def geocode(address: str) -> dict:
    """
    Try ORS geocoding first (global coverage),
    then fall back to Nominatim + offline DB.
    """
    # Try coordinate input directly: "28.63, 77.21"
    import re
    if re.match(r"^\s*-?\d+\.?\d*\s*,\s*-?\d+\.?\d*\s*$", address):
        return _nominatim_geocode(address)

    # Try ORS geocoding
    if ORS_API_KEY:
        try:
            resp = requests.get(
                f"{ORS_BASE}/geocode/search",
                params={"api_key": ORS_API_KEY, "text": address, "size": 1},
                timeout=8,
            )
            resp.raise_for_status()
            features = resp.json().get("features", [])
            if features:
                lon, lat = features[0]["geometry"]["coordinates"]
                label = features[0]["properties"].get("label", address)
                return {"lat": lat, "lon": lon, "display_name": label}
        except Exception:
            pass

    # Fall back to Nominatim + offline DB
    return _nominatim_geocode(address)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _nearest_node_manual(G, lat, lon):
    best, best_d = None, float("inf")
    for nid, data in G.nodes(data=True):
        d = _haversine(lat, lon, data["y"], data["x"])
        if d < best_d:
            best_d = d
            best = nid
    return best


def _ox_nearest_node(G, lon, lat):
    import osmnx as ox
    return ox.nearest_nodes(G, lon, lat)


def _add_balanced_weights(G, traffic_mult):
    for u, v, k, data in G.edges(keys=True, data=True):
        dist = data.get("length", 100)
        time = data.get("travel_time", dist / 14) * traffic_mult
        G[u][v][k]["balanced"] = 0.4 * dist + 0.6 * time * 14


def _try_osmnx(center_lat, center_lon, radius_m):
    try:
        import osmnx as ox
        ox.settings.log_console = False
        G = ox.graph_from_point(
            (center_lat, center_lon),
            dist=radius_m,
            network_type="drive",
            simplify=True,
        )
        G = ox.add_edge_speeds(G)
        G = ox.add_edge_travel_times(G)
        return G, False
    except Exception:
        return None, True


# ── ORS routing ───────────────────────────────────────────────────────────────

def _ors_directions(olon, olat, dlon, dlat, profile="driving-car", extra_params=None):
    """
    Call ORS directions and return (coords, distance_km, duration_min) or None.
    """
    body = {
        "coordinates": [[olon, olat], [dlon, dlat]],
        "instructions": False,
    }
    if extra_params:
        body.update(extra_params)
    try:
        resp = requests.post(
            f"{ORS_BASE}/v2/directions/{profile}/geojson",
            json=body,
            headers=ORS_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        data     = resp.json()
        feature  = data["features"][0]
        coords   = [(c[1], c[0]) for c in feature["geometry"]["coordinates"]]
        summary  = feature["properties"]["summary"]
        dist_km  = round(summary["distance"] / 1000, 2)
        dur_min  = round(summary["duration"] / 60, 1)
        return coords, dist_km, dur_min
    except Exception:
        return None


def _build_long_distance_routes(origin, dest, traffic_mult, weather_mult, vehicle_type="economy"):
    """
    Fetch 3 REAL routes from ORS using different parameter sets:
      - Fastest: default (ORS optimises for time)
      - Shortest: preference=shortest
      - Optimal: avoid_features=[ferries], recommended profile
    Falls back to straight-line estimates if ORS fails.
    """
    olat, olon = origin["lat"], origin["lon"]
    dlat, dlon = dest["lat"], dest["lon"]

    def _interpolate(n=60):
        return [
            (olat + (dlat - olat) * i / (n - 1),
             olon + (dlon - olon) * i / (n - 1))
            for i in range(n)
        ]

    combined_mult = traffic_mult * weather_mult

    # ── Fetch 3 variants ──────────────────────────────────────────────────────
    fastest_raw  = _ors_directions(olon, olat, dlon, dlat)
    shortest_raw = _ors_directions(olon, olat, dlon, dlat,
                                   extra_params={"preference": "shortest"})
    # Recommended = fastest but avoiding highways (more scenic/balanced)
    optimal_raw  = _ors_directions(olon, olat, dlon, dlat,
                                   extra_params={"preference": "recommended"})

    source = "OpenRouteService" if fastest_raw else "Estimated (straight-line)"

    def _make_route(rtype, raw, speed_kmh, mult):
        if raw:
            coords, dist_km, dur_min = raw
            # Apply traffic + weather on top of ORS duration
            adjusted_min = round(dur_min * mult, 1)
        else:
            # Fallback interpolation
            coords  = _interpolate()
            dist_km = round(sum(
                _haversine(coords[i][0], coords[i][1], coords[i+1][0], coords[i+1][1])
                for i in range(len(coords) - 1)
            ), 2)
            adjusted_min = round((dist_km / speed_kmh) * 60 * mult, 1)

        fare = calculate_fare(dist_km, adjusted_min, vehicle_type=vehicle_type)
        return {
            "route_type":     rtype,
            "label":          rtype.capitalize(),
            "distance_km":    dist_km,
            "time_min":       adjusted_min,
            "fare_total":     fare["total"],
            "fare_breakdown": fare,
            "coords":         coords,
            "node_count":     len(coords),
            "source":         source,
        }

    return [
        _make_route("fastest",  fastest_raw,  90.0, combined_mult),
        _make_route("shortest", shortest_raw, 70.0, 1.0),
        _make_route("optimal",  optimal_raw,  80.0, combined_mult * 0.9),
    ]


# ── Main RouteService ─────────────────────────────────────────────────────────

class RouteService:
    def __init__(self):
        self._cache = {}

    def find_routes(
        self,
        origin_address: str,
        dest_address: str,
        weather_condition: str = "clear",
        use_traffic: bool = True,
        vehicle_type: str = "economy",
    ) -> dict:

        # 1. Geocode (ORS global → Nominatim fallback)
        origin = geocode(origin_address)
        dest   = geocode(dest_address)

        dist_km    = _haversine(origin["lat"], origin["lon"], dest["lat"], dest["lon"])
        is_long    = dist_km > 50
        session_id = uuid.uuid4().hex[:8]

        # 2. Traffic & weather
        traffic = get_traffic_info(
            origin["lat"], origin["lon"], dest["lat"], dest["lon"]
        )
        traffic_mult  = traffic["multiplier"] if use_traffic else 1.0
        weather       = simulate_weather(weather_condition)
        weather_mult  = 1.0 / max(weather["speed_factor"], 0.1)
        combined_mult = traffic_mult * weather_mult

        # ── Long-distance mode (> 50 km) ──────────────────────────────────────
        if is_long:
            route_results = _build_long_distance_routes(
                origin, dest, traffic_mult, weather_mult, vehicle_type
            )
            graph_source = "OpenRouteService API" if ORS_API_KEY else "Estimated"

        # ── Short-distance mode (<= 50 km): OSMnx + A*/Dijkstra ───────────────
        else:
            radius_m   = min(max(int(dist_km * 800), 2500), 50000)
            center_lat = (origin["lat"] + dest["lat"]) / 2
            center_lon = (origin["lon"] + dest["lon"]) / 2

            cache_key = f"{center_lat:.3f}_{center_lon:.3f}_{radius_m}"
            if cache_key not in self._cache:
                G, is_demo = _try_osmnx(center_lat, center_lon, radius_m)
                if G is None:
                    G = get_demo_graph(center_lat, center_lon)
                    is_demo = True
                self._cache[cache_key] = (G, is_demo)

            G, is_demo = self._cache[cache_key]
            graph_source = "OpenStreetMap (live)" if not is_demo else "Synthetic demo graph"

            if is_demo:
                o_node = _nearest_node_manual(G, origin["lat"], origin["lon"])
                d_node = _nearest_node_manual(G, dest["lat"],   dest["lon"])
            else:
                o_node = _ox_nearest_node(G, origin["lon"], origin["lat"])
                d_node = _ox_nearest_node(G, dest["lon"],   dest["lat"])

            if o_node == d_node:
                raise ValueError(
                    "Origin and destination map to the same road node. "
                    "Please choose locations further apart."
                )

            _add_balanced_weights(G, traffic_mult)

            routes_spec = [
                ("fastest",  lambda: astar(G,    o_node, d_node, weight="travel_time"), combined_mult),
                ("shortest", lambda: dijkstra(G, o_node, d_node, weight="length"),       1.0),
                ("optimal",  lambda: astar(G,    o_node, d_node, weight="balanced"),     combined_mult * 0.9),
            ]

            route_results = []
            for rtype, compute_fn, mult in routes_spec:
                try:
                    path, _ = compute_fn()
                    if not path or len(path) < 2:
                        continue
                    metrics = compute_path_metrics(G, path, traffic_multiplier=mult)
                    fare    = calculate_fare(metrics["distance_km"], metrics["time_min"], vehicle_type=vehicle_type)
                    route_results.append({
                        "route_type":     rtype,
                        "label":          rtype.capitalize(),
                        "distance_km":    metrics["distance_km"],
                        "time_min":       metrics["time_min"],
                        "fare_total":     fare["total"],
                        "fare_breakdown": fare,
                        "coords":         metrics["coords"],
                        "node_count":     len(path),
                    })
                except Exception:
                    traceback.print_exc()

        if not route_results:
            raise ValueError(
                "No route could be found between these locations. "
                "Try being more specific, e.g. add the city name."
            )

        recommended = recommend_route(route_results)

        map_url = render_map(
            origin_coords=(origin["lat"], origin["lon"]),
            dest_coords=(dest["lat"],    dest["lon"]),
            routes=route_results,
            origin_name=origin_address,
            dest_name=dest_address,
            session_id=session_id,
        )

        return {
            "origin":       origin,
            "destination":  dest,
            "routes":       route_results,
            "traffic":      traffic,
            "weather":      weather,
            "recommended":  recommended,
            "map_url":      map_url,
            "session_id":   session_id,
            "graph_source": graph_source,
            "dist_km":      round(dist_km, 2),
        }