import pytest


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_samples.db")


@pytest.fixture
def sample_config(tmp_path, db_path):
    return {
        "google_maps_api_key": "TEST_KEY",
        "db_path": db_path,
        "travel_mode": "DRIVE",
        "locations": {
            "a": {"lat": 20.6, "lng": -103.3, "label": "Punto A"},
            "b": {"lat": 20.7, "lng": -103.4, "label": "Punto B"},
        },
        "routes": [
            {"id": "a_to_b", "origin": "a", "destination": "b"},
        ],
    }
