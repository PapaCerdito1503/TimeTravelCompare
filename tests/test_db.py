from pathlib import Path

from tracker.db import connect, init_db, insert_sample


def test_init_db_creates_file_and_schema(db_path):
    init_db(db_path)
    assert Path(db_path).exists()
    with connect(db_path) as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(samples)")}
    expected = {
        "id", "sampled_at", "route_id", "origin_label", "destination_label",
        "duration_sec", "static_duration_sec", "distance_m",
        "travel_mode", "raw_json", "error",
    }
    assert expected.issubset(cols)


def test_init_db_is_idempotent(db_path):
    init_db(db_path)
    init_db(db_path)
    with connect(db_path) as conn:
        n = conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
    assert n == 0


def test_init_db_creates_expected_indexes(db_path):
    init_db(db_path)
    with connect(db_path) as conn:
        idx = {r[1] for r in conn.execute("PRAGMA index_list('samples')")}
    assert "idx_samples_route_time" in idx
    assert "idx_samples_time" in idx


def test_insert_sample_round_trip(db_path):
    init_db(db_path)
    with connect(db_path) as conn:
        insert_sample(
            conn,
            sampled_at="2026-05-11T13:00:00+00:00",
            route_id="a_to_b",
            origin_label="A",
            destination_label="B",
            duration_sec=1200,
            static_duration_sec=900,
            distance_m=5400,
            travel_mode="DRIVE",
            raw_json='{"x":1}',
        )
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM samples").fetchone()
    assert row["route_id"] == "a_to_b"
    assert row["duration_sec"] == 1200
    assert row["error"] is None


def test_insert_sample_with_error(db_path):
    init_db(db_path)
    with connect(db_path) as conn:
        insert_sample(
            conn,
            sampled_at="2026-05-11T13:00:00+00:00",
            route_id="a_to_b",
            origin_label="A",
            destination_label="B",
            duration_sec=0,
            static_duration_sec=None,
            distance_m=0,
            travel_mode="DRIVE",
            raw_json="{}",
            error="HTTP 500",
        )
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM samples").fetchone()
    assert row["error"] == "HTTP 500"
    assert row["static_duration_sec"] is None
