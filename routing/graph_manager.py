"""
Graph manager: downloads OSMnx road network,
caches it, and provides nearest-node lookup.
"""

import os
import math
import pickle
import osmnx as ox
import networkx as nx

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "graph_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

ox.settings.log_console = False
ox.settings.use_cache = True


def _cache_path(city: str) -> str:
    safe = city.lower().replace(" ", "_").replace(",", "")
    return os.path.join(CACHE_DIR, f"{safe}.pkl")


def get_graph(city: str, network_type: str = "drive"):
    """
    Load from cache or download OSMnx drive network for a city.
    Returns a projected MultiDiGraph with travel_time edge weights added.
    """
    cp = _cache_path(city)
    if os.path.exists(cp):
        with open(cp, "rb") as f:
            G = pickle.load(f)
        return G

    G = ox.graph_from_place(city, network_type=network_type, simplify=True)
    G = ox.add_edge_speeds(G)
    G = ox.add_edge_travel_times(G)
    with open(cp, "wb") as f:
        pickle.dump(G, f)
    return G


def get_nearest_node(G, lat: float, lon: float):
    """Return the graph node ID nearest to (lat, lon)."""
    return ox.nearest_nodes(G, lon, lat)


def get_node_coords(G, node_id) -> tuple:
    """Return (lat, lon) for a graph node."""
    d = G.nodes[node_id]
    return d["y"], d["x"]


def add_traffic_weights(G, traffic_data: dict):
    """
    Modify edge travel_time weights using a traffic_data dict.
    traffic_data: {edge_key: multiplier}  (e.g. 1.5 = 50% slower)
    Returns modified graph copy.
    """
    H = G.copy()
    for u, v, k, data in H.edges(keys=True, data=True):
        key = (u, v)
        mult = traffic_data.get(key, 1.0)
        if "travel_time" in data:
            H[u][v][k]["travel_time_traffic"] = data["travel_time"] * mult
        else:
            H[u][v][k]["travel_time_traffic"] = data.get("length", 10) / 50 * 3.6 * mult
    return H
