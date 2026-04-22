"""
Map visualization using Folium.
Renders multi-route overlays with markers and polylines.
"""

import folium
from folium.plugins import MarkerCluster, MiniMap, Fullscreen
import os

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "maps")
os.makedirs(OUTPUT_DIR, exist_ok=True)


ROUTE_STYLES = {
    "fastest": {
        "color": "#00c853",
        "weight": 6,
        "opacity": 0.9,
        "dash_array": None,
        "label": "🟢 Fastest Route",
    },
    "shortest": {
        "color": "#2979ff",
        "weight": 6,
        "opacity": 0.9,
        "dash_array": "8 4",
        "label": "🔵 Shortest Route",
    },
    "optimal": {
        "color": "#ff6d00",
        "weight": 7,
        "opacity": 1.0,
        "dash_array": None,
        "label": "🟠 Optimal Route",
    },
}


def render_map(
    origin_coords: tuple,
    dest_coords: tuple,
    routes: list,
    origin_name: str = "Origin",
    dest_name: str = "Destination",
    session_id: str = "default",
) -> str:
    """
    Create a Folium map with all routes overlaid.

    routes: list of dicts with keys:
        - route_type: "fastest" | "shortest" | "optimal"
        - coords: list of (lat, lon)
        - distance_km, time_min, fare_total

    Returns: relative URL path to saved HTML map.
    """
    center_lat = (origin_coords[0] + dest_coords[0]) / 2
    center_lon = (origin_coords[1] + dest_coords[1]) / 2

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=13,
        tiles=None,
    )

    # Tile layers
    folium.TileLayer(
        "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
        attr="© OpenStreetMap © CARTO",
        name="Dark Map",
        max_zoom=20,
    ).add_to(m)

    folium.TileLayer(
        "OpenStreetMap",
        name="Street Map",
    ).add_to(m)

    folium.TileLayer(
        "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        attr="© OpenStreetMap © CARTO",
        name="Light Map",
        max_zoom=20,
    ).add_to(m)

    # Add routes (draw in reverse so optimal is on top)
    for route in reversed(routes):
        rtype = route.get("route_type", "optimal")
        style = ROUTE_STYLES.get(rtype, ROUTE_STYLES["optimal"])
        coords = route.get("coords", [])
        if len(coords) < 2:
            continue

        tooltip_text = (
            f"<b>{style['label']}</b><br>"
            f"📏 {route.get('distance_km', 0):.1f} km<br>"
            f"⏱ {route.get('time_min', 0):.0f} min<br>"
            f"💰 ${route.get('fare_total', 0):.2f}"
        )

        kwargs = dict(
            locations=coords,
            color=style["color"],
            weight=style["weight"],
            opacity=style["opacity"],
            tooltip=folium.Tooltip(tooltip_text, sticky=True),
            popup=folium.Popup(tooltip_text, max_width=200),
        )
        if style["dash_array"]:
            kwargs["dash_array"] = style["dash_array"]

        folium.PolyLine(**kwargs).add_to(m)

    # Start marker
    folium.Marker(
        location=list(origin_coords),
        popup=folium.Popup(f"<b>🚀 Start</b><br>{origin_name}", max_width=200),
        tooltip=f"Start: {origin_name}",
        icon=folium.Icon(color="green", icon="play", prefix="fa"),
    ).add_to(m)

    # End marker
    folium.Marker(
        location=list(dest_coords),
        popup=folium.Popup(f"<b>🏁 End</b><br>{dest_name}", max_width=200),
        tooltip=f"End: {dest_name}",
        icon=folium.Icon(color="red", icon="flag", prefix="fa"),
    ).add_to(m)

    # Fit bounds
    all_coords = [list(origin_coords), list(dest_coords)]
    for route in routes:
        all_coords.extend(route.get("coords", []))
    if all_coords:
        lats = [c[0] for c in all_coords]
        lons = [c[1] for c in all_coords]
        m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])

    # Plugins
    MiniMap(toggle_display=True).add_to(m)
    Fullscreen(position="topright").add_to(m)
    folium.LayerControl(position="bottomright").add_to(m)

    # Legend
    legend_html = _build_legend(routes)
    m.get_root().html.add_child(folium.Element(legend_html))

    # Save
    filename = f"map_{session_id}.html"
    filepath = os.path.join(OUTPUT_DIR, filename)
    m.save(filepath)
    return f"/static/maps/{filename}"


def _build_legend(routes: list) -> str:
    items = ""
    for route in routes:
        rtype = route.get("route_type", "optimal")
        style = ROUTE_STYLES.get(rtype, ROUTE_STYLES["optimal"])
        items += (
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">'
            f'<div style="width:28px;height:4px;background:{style["color"]};border-radius:2px"></div>'
            f'<span style="font-size:12px">{style["label"]}</span>'
            f"</div>"
        )

    return f"""
    <div style="
        position: fixed; bottom: 50px; left: 50px; z-index: 1000;
        background: rgba(15,15,25,0.92); color: #eee;
        padding: 14px 18px; border-radius: 10px;
        border: 1px solid rgba(255,255,255,0.1);
        font-family: 'Segoe UI', sans-serif;
        backdrop-filter: blur(8px);
        box-shadow: 0 4px 24px rgba(0,0,0,0.5);
        min-width: 180px;
    ">
        <div style="font-weight:700;font-size:13px;margin-bottom:10px;
                    border-bottom:1px solid rgba(255,255,255,0.15);padding-bottom:6px;">
            🗺 Route Legend
        </div>
        {items}
    </div>
    """
