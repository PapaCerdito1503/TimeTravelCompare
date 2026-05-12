from unittest.mock import MagicMock, patch

import pytest

from tracker.routes_api import (
    FIELD_MASK,
    ROUTES_ENDPOINT,
    RoutesApiError,
    _parse_duration,
    compute_route,
)


def _mock_response(status_code=200, json_body=None, text=""):
    resp = MagicMock()
    resp.ok = status_code < 400
    resp.status_code = status_code
    resp.text = text
    resp.json.return_value = json_body or {}
    return resp


def test_parse_duration_strips_s():
    assert _parse_duration("1234s") == 1234


def test_parse_duration_handles_zero_and_empty():
    assert _parse_duration("") == 0
    assert _parse_duration("0s") == 0


def test_compute_route_happy_path():
    body = {
        "routes": [
            {"duration": "1500s", "staticDuration": "1200s", "distanceMeters": 7800}
        ]
    }
    with patch("tracker.routes_api.requests.post") as mock_post:
        mock_post.return_value = _mock_response(200, body)
        result = compute_route(
            api_key="K", origin_lat=1.0, origin_lng=2.0,
            dest_lat=3.0, dest_lng=4.0,
        )
    assert result["duration_sec"] == 1500
    assert result["static_duration_sec"] == 1200
    assert result["distance_m"] == 7800
    assert result["raw"] == body


def test_compute_route_sends_correct_headers_and_body():
    body = {"routes": [{"duration": "10s", "staticDuration": "10s", "distanceMeters": 100}]}
    with patch("tracker.routes_api.requests.post") as mock_post:
        mock_post.return_value = _mock_response(200, body)
        compute_route(
            api_key="MY_KEY",
            origin_lat=20.0, origin_lng=-103.0,
            dest_lat=21.0, dest_lng=-104.0,
            travel_mode="DRIVE",
        )
    args, kwargs = mock_post.call_args
    assert args[0] == ROUTES_ENDPOINT
    assert kwargs["headers"]["X-Goog-Api-Key"] == "MY_KEY"
    assert kwargs["headers"]["X-Goog-FieldMask"] == FIELD_MASK
    payload = kwargs["json"]
    assert payload["origin"]["location"]["latLng"]["latitude"] == 20.0
    assert payload["destination"]["location"]["latLng"]["longitude"] == -104.0
    assert payload["travelMode"] == "DRIVE"
    assert payload["routingPreference"] == "TRAFFIC_AWARE_OPTIMAL"


def test_compute_route_raises_on_http_error():
    with patch("tracker.routes_api.requests.post") as mock_post:
        mock_post.return_value = _mock_response(500, text="server error")
        with pytest.raises(RoutesApiError, match="HTTP 500"):
            compute_route(
                api_key="K", origin_lat=1.0, origin_lng=2.0,
                dest_lat=3.0, dest_lng=4.0,
            )


def test_compute_route_raises_when_no_routes():
    with patch("tracker.routes_api.requests.post") as mock_post:
        mock_post.return_value = _mock_response(200, {"routes": []})
        with pytest.raises(RoutesApiError, match="No routes returned"):
            compute_route(
                api_key="K", origin_lat=1.0, origin_lng=2.0,
                dest_lat=3.0, dest_lng=4.0,
            )
