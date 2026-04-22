"""
Demo graph generator: creates a realistic synthetic road network
for testing when OSM/Overpass API is unavailable.
Simulates a city grid with arterials, highways and residential streets.
"""

import networkx as nx
import math
import random


def _haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def generate_city_graph(
    center_lat=28.6315,
    center_lon=77.2167,
    grid_size=12,
    spacing_m=400,
    seed=42,
):
    """
    Generate a synthetic MultiDiGraph resembling a city road network.
    - Grid backbone (arterial roads)
    - Diagonal shortcuts (express roads)
    - Random residential links
    - Realistic speed / travel_time attributes
    """
    rng = random.Random(seed)
    G = nx.MultiDiGraph()
    G.graph["crs"] = "EPSG:4326"

    # Lat/Lon degree per metre (approximate)
    dlat = spacing_m / 111320
    dlon = spacing_m / (111320 * math.cos(math.radians(center_lat)))

    # ── Build grid nodes ──────────────────────────────────────────────────
    nodes = {}
    for row in range(grid_size):
        for col in range(grid_size):
            nid = row * grid_size + col
            lat = center_lat + (row - grid_size // 2) * dlat
            lon = center_lon + (col - grid_size // 2) * dlon
            G.add_node(nid, y=lat, x=lon, street_count=4)
            nodes[(row, col)] = nid

    # ── Road type assignment ──────────────────────────────────────────────
    def road_type(row, col):
        if row % 4 == 0 or col % 4 == 0:
            return "primary", 60
        elif row % 2 == 0 or col % 2 == 0:
            return "secondary", 40
        else:
            return "residential", 25

    # ── Grid edges (bidirectional) ────────────────────────────────────────
    for row in range(grid_size):
        for col in range(grid_size):
            u = nodes[(row, col)]
            u_lat = G.nodes[u]["y"]
            u_lon = G.nodes[u]["x"]
            rtype, speed = road_type(row, col)

            neighbors = []
            if col + 1 < grid_size:
                neighbors.append((row, col + 1))
            if row + 1 < grid_size:
                neighbors.append((row + 1, col))

            for nr, nc in neighbors:
                v = nodes[(nr, nc)]
                v_lat = G.nodes[v]["y"]
                v_lon = G.nodes[v]["x"]
                length = _haversine(u_lat, u_lon, v_lat, v_lon)
                # Noise
                length *= rng.uniform(0.95, 1.15)
                speed_mps = speed * 1000 / 3600
                travel_time = length / speed_mps

                attrs = dict(
                    length=length,
                    speed_kph=speed,
                    travel_time=travel_time,
                    highway=rtype,
                    oneway=False,
                    name=f"{rtype.capitalize()} St {row}-{col}",
                )
                G.add_edge(u, v, **attrs)
                G.add_edge(v, u, **attrs)

    # ── Diagonal shortcuts (express corridors) ────────────────────────────
    for row in range(0, grid_size - 2, 3):
        for col in range(0, grid_size - 2, 3):
            u = nodes[(row, col)]
            v = nodes[(row + 2, col + 2)]
            u_lat, u_lon = G.nodes[u]["y"], G.nodes[u]["x"]
            v_lat, v_lon = G.nodes[v]["y"], G.nodes[v]["x"]
            length = _haversine(u_lat, u_lon, v_lat, v_lon) * rng.uniform(0.85, 1.05)
            speed = 70
            travel_time = length / (speed * 1000 / 3600)
            attrs = dict(length=length, speed_kph=speed, travel_time=travel_time,
                         highway="trunk", oneway=False, name="Express Corridor")
            G.add_edge(u, v, **attrs)
            G.add_edge(v, u, **attrs)

    # ── Random residential shortcuts ──────────────────────────────────────
    rng2 = random.Random(seed + 1)
    all_nodes = list(nodes.values())
    for _ in range(grid_size * 2):
        u = rng2.choice(all_nodes)
        v = rng2.choice(all_nodes)
        if u == v:
            continue
        u_lat, u_lon = G.nodes[u]["y"], G.nodes[u]["x"]
        v_lat, v_lon = G.nodes[v]["y"], G.nodes[v]["x"]
        length = _haversine(u_lat, u_lon, v_lat, v_lon)
        if length > 3000:
            continue
        length *= rng2.uniform(1.1, 1.5)  # winding road
        speed = 20
        travel_time = length / (speed * 1000 / 3600)
        attrs = dict(length=length, speed_kph=speed, travel_time=travel_time,
                     highway="residential", oneway=False, name="Side Street")
        G.add_edge(u, v, **attrs)
        G.add_edge(v, u, **attrs)

    return G


def get_demo_graph(center_lat=28.6315, center_lon=77.2167):
    """Return a cached demo graph centred on given coords."""
    return generate_city_graph(center_lat, center_lon)
