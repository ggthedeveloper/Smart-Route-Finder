"""
Core routing algorithms: Dijkstra and A* implementation
over OSMnx graph networks with multi-metric support.
"""

import heapq
import math
import networkx as nx
from typing import Optional


def haversine(lat1, lon1, lat2, lon2):
    """Compute great-circle distance (km) between two coordinates."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def dijkstra(G, source, target, weight="length"):
    """
    Dijkstra's shortest path algorithm.
    Returns (path_nodes, total_cost) or (None, inf) if unreachable.
    """
    dist = {source: 0.0}
    prev = {}
    pq = [(0.0, source)]
    visited = set()

    while pq:
        d, u = heapq.heappop(pq)
        if u in visited:
            continue
        visited.add(u)
        if u == target:
            break
        for v, data in G[u].items():
            # Handle multigraph: pick minimum edge weight
            edge_data = data[0] if isinstance(data, dict) and 0 in data else data
            w = edge_data.get(weight, edge_data.get("length", 1.0))
            if w is None:
                w = 1.0
            nd = d + w
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))

    if target not in dist:
        return None, float("inf")

    path = []
    cur = target
    while cur in prev:
        path.append(cur)
        cur = prev[cur]
    path.append(source)
    path.reverse()
    return path, dist[target]


def astar(G, source, target, weight="length"):
    """
    A* algorithm with haversine heuristic.
    Returns (path_nodes, total_cost) or (None, inf) if unreachable.
    """
    def heuristic(u, v):
        u_data = G.nodes[u]
        v_data = G.nodes[v]
        if "y" in u_data and "x" in u_data:
            return haversine(u_data["y"], u_data["x"], v_data["y"], v_data["x"])
        return 0.0

    open_set = [(0.0, source)]
    g = {source: 0.0}
    f = {source: heuristic(source, target)}
    prev = {}
    closed = set()

    while open_set:
        _, u = heapq.heappop(open_set)
        if u in closed:
            continue
        if u == target:
            break
        closed.add(u)
        for v, data in G[u].items():
            edge_data = data[0] if isinstance(data, dict) and 0 in data else data
            w = edge_data.get(weight, edge_data.get("length", 1.0))
            if w is None:
                w = 1.0
            ng = g[u] + w
            if ng < g.get(v, float("inf")):
                g[v] = ng
                f[v] = ng + heuristic(v, target)
                prev[v] = u
                heapq.heappush(open_set, (f[v], v))

    if target not in g:
        return None, float("inf")

    path = []
    cur = target
    while cur in prev:
        path.append(cur)
        cur = prev[cur]
    path.append(source)
    path.reverse()
    return path, g[target]


def compute_path_metrics(G, path, traffic_multiplier=1.0):
    """
    Given a path (list of node IDs), compute:
    - total_distance_km
    - total_time_min  (assuming avg 50 km/h adjusted by traffic)
    - coords list of (lat, lon) tuples
    """
    if not path or len(path) < 2:
        return {"distance_km": 0, "time_min": 0, "coords": []}

    total_length = 0.0
    coords = []

    for i in range(len(path) - 1):
        u, v = path[i], path[i + 1]
        # Get edge data (multigraph safe)
        edge_dict = G[u][v]
        edge_data = edge_dict[0] if 0 in edge_dict else next(iter(edge_dict.values()))
        total_length += edge_data.get("length", 0) or 0

        # Collect geometry coords
        if "geometry" in edge_data:
            geom = edge_data["geometry"]
            for pt in geom.coords:
                coords.append((pt[1], pt[0]))
        else:
            nu = G.nodes[u]
            nv = G.nodes[v]
            coords.append((nu["y"], nu["x"]))
            coords.append((nv["y"], nv["x"]))

    total_km = total_length / 1000.0
    avg_speed_kmh = 50.0 / max(traffic_multiplier, 0.1)
    total_time_min = (total_km / avg_speed_kmh) * 60.0

    return {
        "distance_km": round(total_km, 2),
        "time_min": round(total_time_min, 1),
        "coords": coords,
    }
