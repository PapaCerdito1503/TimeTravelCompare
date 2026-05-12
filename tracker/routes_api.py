import requests

ROUTES_ENDPOINT = "https://routes.googleapis.com/directions/v2:computeRoutes"

FIELD_MASK = ",".join([
    "routes.duration",
    "routes.staticDuration",
    "routes.distanceMeters",
])


class RoutesApiError(Exception):
    pass


def compute_route(
    *,
    api_key: str,
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    travel_mode: str = "DRIVE",
    timeout: int = 15,
) -> dict:
    """
    Calls Google Routes API and returns parsed result.

    Returns dict with keys:
      duration_sec: int (with live traffic)
      static_duration_sec: int (without traffic)
      distance_m: int
      raw: full JSON response
    """
    body = {
        "origin": {"location": {"latLng": {"latitude": origin_lat, "longitude": origin_lng}}},
        "destination": {"location": {"latLng": {"latitude": dest_lat, "longitude": dest_lng}}},
        "travelMode": travel_mode,
        "routingPreference": "TRAFFIC_AWARE_OPTIMAL",
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }

    resp = requests.post(ROUTES_ENDPOINT, json=body, headers=headers, timeout=timeout)
    if not resp.ok:
        raise RoutesApiError(f"HTTP {resp.status_code}: {resp.text}")

    data = resp.json()
    routes = data.get("routes") or []
    if not routes:
        raise RoutesApiError(f"No routes returned: {data}")

    route = routes[0]
    duration_str = route.get("duration", "0s")
    static_str = route.get("staticDuration", "0s")

    return {
        "duration_sec": _parse_duration(duration_str),
        "static_duration_sec": _parse_duration(static_str),
        "distance_m": int(route.get("distanceMeters", 0)),
        "raw": data,
    }


def _parse_duration(s: str) -> int:
    """API returns durations like '1234s'."""
    if not s:
        return 0
    if s.endswith("s"):
        s = s[:-1]
    return int(float(s))
