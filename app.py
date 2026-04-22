"""
Smart Route Optimization System - Flask Application
"""

import os
import sys
import json
import traceback

sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from routing.route_service import RouteService
from utils.helpers import (
    geocode, load_history, save_to_history, reverse_geocode, get_city_suggestions
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "smart_route_2024_secret")

_route_service = RouteService()


# ── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    history = load_history()
    return render_template("index.html", history=history[-5:][::-1])


@app.route("/route", methods=["POST"])
def find_route():
    origin = request.form.get("origin", "").strip()
    destination = request.form.get("destination", "").strip()
    weather = request.form.get("weather", "clear")
    vehicle_type = request.form.get("vehicle_type", "economy")
    # Checkbox sends value only when checked; hidden input sends "false" when unchecked
    use_traffic = request.form.get("use_traffic", "false") in ("true", "on", "1")

    if not origin or not destination:
        return render_template(
            "index.html",
            error="Please enter both origin and destination.",
            history=load_history()[-5:][::-1],
        )

    try:
        result = _route_service.find_routes(
            origin_address=origin,
            dest_address=destination,
            weather_condition=weather,
            use_traffic=use_traffic,
            vehicle_type=vehicle_type,
        )
        save_to_history(origin, destination)
        session["last_result"] = _serialize_result(result)
        return render_template("results.html", result=result, origin=origin, destination=destination)

    except ValueError as e:
        return render_template(
            "index.html",
            error=str(e),
            history=load_history()[-5:][::-1],
            prefill_origin=origin,
            prefill_dest=destination,
        )
    except Exception as e:
        traceback.print_exc()
        return render_template(
            "index.html",
            error=f"Routing failed: {str(e)[:200]}",
            history=load_history()[-5:][::-1],
            prefill_origin=origin,
            prefill_dest=destination,
        )


@app.route("/map/<session_id>")
def map_view(session_id):
    map_path = f"/static/maps/map_{session_id}.html"
    return render_template("map_view.html", map_url=map_path, session_id=session_id)


@app.route("/geocode")
def geocode_api():
    """JSON API: geocode an address."""
    address = request.args.get("address", "")
    if not address:
        return jsonify({"error": "No address provided"}), 400
    try:
        result = geocode(address)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@app.route("/suggestions")
def suggestions_api():
    """JSON API: get city suggestions for autocomplete."""
    query = request.args.get("q", "").strip()
    if not query or len(query) < 1:
        return jsonify([])
    try:
        suggestions = get_city_suggestions(query, limit=8)
        return jsonify(suggestions)
    except Exception as e:
        return jsonify([]), 400


@app.route("/reverse-geocode")
def reverse_geocode_api():
    """JSON API: reverse geocode coordinates."""
    try:
        lat = float(request.args.get("lat"))
        lon = float(request.args.get("lon"))
        address = reverse_geocode(lat, lon)
        return jsonify({"address": address, "lat": lat, "lon": lon})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/history")
def history():
    return jsonify(load_history())


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "Smart Route Optimizer"})


# ── Helpers ─────────────────────────────────────────────────────────────────

def _serialize_result(result: dict) -> dict:
    """Make result JSON-serializable for session storage."""
    r = dict(result)
    for route in r.get("routes", []):
        route["coords"] = route["coords"][:200]  # Truncate for session
    return json.loads(json.dumps(r, default=str))


@app.route("/ping")
def ping():
    return "OK", 200


if __name__ == "__main__":
    print("🗺  Smart Route Optimization System starting...")
    print("   Open http://localhost:8080 in your browser")

    port = int(os.environ.get("PORT", 8080))  # fallback for local
    app.run(debug=True, host="0.0.0.0", port=port)
