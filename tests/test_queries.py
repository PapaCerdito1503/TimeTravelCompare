import pandas as pd

from tracker.db import connect, init_db, insert_sample
from tracker.queries import (
    daily_median,
    load_samples,
    median_by_dow_hour,
    median_by_hour,
)


def _seed(db_path, rows):
    """rows = list of (sampled_at_utc, route_id, dur_min)."""
    init_db(db_path)
    with connect(db_path) as conn:
        for sampled_at, rid, dur in rows:
            insert_sample(
                conn,
                sampled_at=sampled_at,
                route_id=rid,
                origin_label="A",
                destination_label="B",
                duration_sec=dur * 60,
                static_duration_sec=dur * 60,
                distance_m=5000,
                travel_mode="DRIVE",
                raw_json="{}",
            )


def test_load_samples_returns_dataframe_with_local_time(db_path):
    _seed(db_path, [("2026-05-11T13:00:00+00:00", "r1", 20)])
    df = load_samples(db_path)
    assert isinstance(df, pd.DataFrame)
    assert "duration_min" in df.columns
    assert "local_hour" in df.columns
    assert "local_dow" in df.columns
    assert "local_date" in df.columns
    # 13:00 UTC == 07:00 in America/Mexico_City (UTC-6, no DST in MX since 2022)
    assert df.iloc[0]["local_hour"] == 7
    assert df.iloc[0]["duration_min"] == 20


def test_load_samples_excludes_errored_rows(db_path):
    init_db(db_path)
    with connect(db_path) as conn:
        insert_sample(
            conn, sampled_at="2026-05-11T13:00:00+00:00", route_id="r1",
            origin_label="A", destination_label="B",
            duration_sec=0, static_duration_sec=None, distance_m=0,
            travel_mode="DRIVE", raw_json="{}", error="boom",
        )
        insert_sample(
            conn, sampled_at="2026-05-11T14:00:00+00:00", route_id="r1",
            origin_label="A", destination_label="B",
            duration_sec=600, static_duration_sec=500, distance_m=1000,
            travel_mode="DRIVE", raw_json="{}",
        )
    df = load_samples(db_path)
    assert len(df) == 1
    assert df.iloc[0]["duration_min"] == 10


def test_median_by_hour_groups_by_route_and_hour(db_path):
    _seed(db_path, [
        ("2026-05-11T13:00:00+00:00", "r1", 20),
        ("2026-05-11T13:10:00+00:00", "r1", 22),
        ("2026-05-11T14:00:00+00:00", "r1", 30),
        ("2026-05-11T13:00:00+00:00", "r2", 40),
    ])
    df = median_by_hour(load_samples(db_path))
    row_r1_7 = df[(df["route_id"] == "r1") & (df["local_hour"] == 7)].iloc[0]
    assert row_r1_7["median_min"] == 21
    assert "p25_min" in df.columns
    assert "p75_min" in df.columns


def test_median_by_dow_hour_pivot_shape(db_path):
    _seed(db_path, [
        ("2026-05-11T13:00:00+00:00", "r1", 20),
    ])
    df = median_by_dow_hour(load_samples(db_path), route_id="r1")
    assert "median_min" in df.columns
    assert "local_dow" in df.columns
    assert "local_hour" in df.columns


def test_daily_median_per_route(db_path):
    _seed(db_path, [
        ("2026-05-11T13:00:00+00:00", "r1", 20),
        ("2026-05-11T15:00:00+00:00", "r1", 30),
        ("2026-05-12T13:00:00+00:00", "r1", 25),
    ])
    df = daily_median(load_samples(db_path))
    one_day = df[df["local_date"] == pd.to_datetime("2026-05-11").date()]
    assert one_day.iloc[0]["median_min"] == 25


def test_pair_hourly_savings_positive_when_depa_faster(db_path):
    from tracker.queries import pair_hourly_savings
    _seed(db_path, [
        ("2026-05-11T13:00:00+00:00", "casa", 30),  # local 7
        ("2026-05-11T13:00:00+00:00", "depa", 20),  # local 7
    ])
    out = pair_hourly_savings(load_samples(db_path), "casa", "depa")
    assert len(out) == 1
    assert out.iloc[0]["local_hour"] == 7
    assert out.iloc[0]["savings_min"] == 10
    assert out.iloc[0]["casa_min"] == 30
    assert out.iloc[0]["depa_min"] == 20


def test_pair_hourly_savings_negative_when_casa_faster(db_path):
    from tracker.queries import pair_hourly_savings
    _seed(db_path, [
        ("2026-05-11T13:00:00+00:00", "casa", 20),
        ("2026-05-11T13:00:00+00:00", "depa", 30),
    ])
    out = pair_hourly_savings(load_samples(db_path), "casa", "depa")
    assert out.iloc[0]["savings_min"] == -10


def test_pair_hourly_savings_empty_when_no_common_hours(db_path):
    from tracker.queries import pair_hourly_savings
    _seed(db_path, [
        ("2026-05-11T13:00:00+00:00", "casa", 25),  # local 7
        ("2026-05-11T15:00:00+00:00", "depa", 18),  # local 9
    ])
    out = pair_hourly_savings(load_samples(db_path), "casa", "depa")
    assert out.empty


def test_pair_dow_hour_savings_pivot_shape(db_path):
    from tracker.queries import pair_dow_hour_savings
    _seed(db_path, [
        ("2026-05-11T13:00:00+00:00", "casa", 30),
        ("2026-05-11T13:00:00+00:00", "depa", 20),
    ])
    pivot = pair_dow_hour_savings(load_samples(db_path), "casa", "depa")
    assert pivot.shape == (24, 7)
    # 2026-05-11 was a Monday → dow=0, hour=7 local
    assert pivot.loc[7, 0] == 10
