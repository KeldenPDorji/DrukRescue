"""Pure geo helpers. No PostGIS: Haversine in code is accurate enough at district scale."""

from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two points, in kilometres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def estimate_minutes(distance_km: float, avg_speed_kmh: float, road_factor: float) -> float:
    """Straight-line distance * road_factor (mountain roads wind) at an average speed."""
    return round(distance_km * road_factor / avg_speed_kmh * 60, 1)


def rank_by_distance(origin_lat: float, origin_lng: float, units: list[dict]) -> list[dict]:
    """Return units that have coordinates, nearest first, each with ``distance_km`` added."""
    ranked = []
    for unit in units:
        lat, lng = unit.get("lat"), unit.get("lng")
        if lat is None or lng is None:
            continue
        ranked.append({**unit, "distance_km": round(haversine_km(origin_lat, origin_lng, lat, lng), 3)})
    ranked.sort(key=lambda u: u["distance_km"])
    return ranked
