from datetime import datetime, timezone
from unittest.mock import patch

import yaml

from tracker.db import connect, init_db, insert_sample
from tracker.sample import run_once


def _write_config(tmp_path, cfg):
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(cfg))
    return str(p)


def test_run_once_inserts_one_row_per_route(tmp_path, sample_config):
    cfg_path = _write_config(tmp_path, sample_config)
    fake_result = {
        "duration_sec": 600,
        "static_duration_sec": 500,
        "distance_m": 2000,
        "raw": {"routes": [{"duration": "600s"}]},
    }
    with patch("tracker.sample.compute_route", return_value=fake_result):
        ok = run_once(cfg_path)

    assert ok == 1
    with connect(sample_config["db_path"]) as conn:
        rows = conn.execute("SELECT * FROM samples").fetchall()
    assert len(rows) == 1
    assert rows[0]["route_id"] == "a_to_b"
    assert rows[0]["duration_sec"] == 600
    assert rows[0]["error"] is None


def test_run_once_persists_error_and_continues(tmp_path, sample_config):
    sample_config["routes"] = [
        {"id": "fails", "origin": "a", "destination": "b"},
        {"id": "works", "origin": "a", "destination": "b"},
    ]
    cfg_path = _write_config(tmp_path, sample_config)
    fake_result = {
        "duration_sec": 600, "static_duration_sec": 500,
        "distance_m": 2000, "raw": {},
    }
    call_count = {"n": 0}

    def fake_compute(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("boom")
        return fake_result

    with patch("tracker.sample.compute_route", side_effect=fake_compute):
        ok = run_once(cfg_path)

    assert ok == 1
    with connect(sample_config["db_path"]) as conn:
        rows = conn.execute(
            "SELECT route_id, error FROM samples ORDER BY route_id"
        ).fetchall()
    assert [(r["route_id"], r["error"] is not None) for r in rows] == [
        ("fails", True),
        ("works", False),
    ]


def test_cost_guard_aborts_when_limit_reached(tmp_path, sample_config):
    sample_config["max_monthly_calls"] = 1
    cfg_path = _write_config(tmp_path, sample_config)

    fake_result = {
        "duration_sec": 600, "static_duration_sec": 500,
        "distance_m": 2000, "raw": {},
    }
    init_db(sample_config["db_path"])
    now_utc = datetime.now(timezone.utc).isoformat()
    with connect(sample_config["db_path"]) as conn:
        insert_sample(
            conn, sampled_at=now_utc, route_id="seed",
            origin_label="A", destination_label="B",
            duration_sec=1, static_duration_sec=1, distance_m=1,
            travel_mode="DRIVE", raw_json="{}",
        )

    with patch("tracker.sample.compute_route", return_value=fake_result) as m:
        ok = run_once(cfg_path)

    assert ok == 0
    assert m.call_count == 0


def test_cost_guard_disabled_by_default(tmp_path, sample_config):
    cfg_path = _write_config(tmp_path, sample_config)
    fake_result = {
        "duration_sec": 600, "static_duration_sec": 500,
        "distance_m": 2000, "raw": {},
    }
    with patch("tracker.sample.compute_route", return_value=fake_result):
        ok = run_once(cfg_path)
    assert ok == 1
