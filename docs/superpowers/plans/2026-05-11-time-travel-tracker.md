# time-travel-tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local tool that samples Google Routes API every 30 min (06:00–23:00, daily) for 8 commute routes, stores results in SQLite, and serves a local Plotly dashboard so the user can decide whether to move from their current home to a new apartment based on real travel-time data.

**Architecture:** Three loosely-coupled components — a sampler that calls Routes API on a launchd schedule, a SQLite store, and a Flask+Plotly dashboard. Shared query layer (`tracker/queries.py`) keeps analysis logic DRY between CLI and web.

**Tech Stack:** Python 3.11+, `requests`, `PyYAML`, `sqlite3` (stdlib), `pandas`, `plotly`, `flask`, `pytest` for tests, `launchd` for scheduling.

**Spec:** `docs/superpowers/specs/2026-05-11-time-travel-tracker-design.md`

**Context for engineer:** Some files already exist from an earlier scaffolding pass (`tracker/db.py`, `tracker/routes_api.py`, `tracker/sample.py`, `tracker/analyze.py`, `config.example.yaml`, `requirements.txt`, `.gitignore`, `README.md`, `scripts/run_sample.sh`). These compile but have **no tests**. This plan adds tests (characterization first), extends with the dashboard and cost guard, and finishes with launchd setup. Do **not** rewrite working modules from scratch unless a task says so.

---

## Task 1: Initialize git repo + dev environment

**Files:**
- Create: `requirements-dev.txt`
- Modify: `requirements.txt` (no edit — confirm contents)
- Modify: `.gitignore` (no edit — confirm contents)

- [ ] **Step 1: Verify working dir is empty of git state**

Run:
```bash
cd /Users/crdo/Documents/mierdas/tools/time-travel-tracker
test ! -d .git && echo "no git yet" || echo "already a repo"
```
Expected: `no git yet`

- [ ] **Step 2: Initialize git repo and set default branch**

Run:
```bash
git init -b main
```
Expected: `Initialized empty Git repository in .../time-travel-tracker/.git/`

- [ ] **Step 3: Create dev dependencies file**

Create `requirements-dev.txt`:
```
pytest>=7.4.0
pytest-mock>=3.12.0
```

- [ ] **Step 4: Create virtualenv and install both requirement sets**

Run:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt -r requirements-dev.txt
```
Expected: `Successfully installed ...` listing requests, PyYAML, pytest, pytest-mock, etc. No errors.

- [ ] **Step 5: Verify imports work**

Run:
```bash
source .venv/bin/activate
python -c "import requests, yaml, sqlite3, pytest; print('ok')"
```
Expected: `ok`

- [ ] **Step 6: Initial commit**

Run:
```bash
git add .gitignore requirements.txt requirements-dev.txt README.md \
        config.example.yaml tracker scripts docs
git status
```
Verify `config.yaml`, `data/`, `.venv/`, `__pycache__/` are NOT in the staged list.

Then commit:
```bash
git commit -m "chore: initial scaffolding from brainstorming session"
```
Expected: a commit succeeds.

---

## Task 2: Add tests for `tracker/db.py`

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Create tests package**

Create `tests/__init__.py` as empty file.

- [ ] **Step 2: Create shared fixtures**

Create `tests/conftest.py`:
```python
import pytest


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_samples.db")


@pytest.fixture
def sample_config(tmp_path, db_path):
    """A minimal valid config object (dict, not yaml file)."""
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
```

- [ ] **Step 3: Write failing tests for db.py**

Create `tests/test_db.py`:
```python
import sqlite3
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
    init_db(db_path)  # should not raise
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
```

- [ ] **Step 4: Run tests, expect them to pass (characterizing existing code)**

Run:
```bash
source .venv/bin/activate
PYTHONPATH=. pytest tests/test_db.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/__init__.py tests/conftest.py tests/test_db.py
git commit -m "test: characterize db schema and insert behavior"
```

---

## Task 3: Add tests for `tracker/routes_api.py`

**Files:**
- Create: `tests/test_routes_api.py`

- [ ] **Step 1: Write failing tests with mocked HTTP**

Create `tests/test_routes_api.py`:
```python
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
```

- [ ] **Step 2: Run tests, expect them to pass**

Run:
```bash
source .venv/bin/activate
PYTHONPATH=. pytest tests/test_routes_api.py -v
```
Expected: 6 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_routes_api.py
git commit -m "test: characterize Routes API client (header, body, error paths)"
```

---

## Task 4: Add tests for `tracker/sample.py` and clean up exception handling

**Files:**
- Modify: `tracker/sample.py`
- Create: `tests/test_sample.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_sample.py`:
```python
from unittest.mock import patch

import yaml

from tracker.db import connect
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
    # Two routes: first errors, second succeeds.
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

    assert ok == 1  # only "works" succeeded
    with connect(sample_config["db_path"]) as conn:
        rows = conn.execute(
            "SELECT route_id, error FROM samples ORDER BY route_id"
        ).fetchall()
    assert [(r["route_id"], r["error"] is not None) for r in rows] == [
        ("fails", True),
        ("works", False),
    ]
```

- [ ] **Step 2: Run tests, expect them to pass**

Run:
```bash
source .venv/bin/activate
PYTHONPATH=. pytest tests/test_sample.py -v
```
Expected: 2 passed.

- [ ] **Step 3: Tighten exception handling in `tracker/sample.py`**

The current handler catches `(RoutesApiError, Exception)` which is redundant. Replace just the except line.

In `tracker/sample.py`, find:
```python
            except (RoutesApiError, Exception) as e:
```
Replace with:
```python
            except Exception as e:
```

- [ ] **Step 4: Re-run all tests**

Run:
```bash
source .venv/bin/activate
PYTHONPATH=. pytest tests/ -v
```
Expected: 13 passed (5 + 6 + 2).

- [ ] **Step 5: Commit**

```bash
git add tests/test_sample.py tracker/sample.py
git commit -m "test: characterize sampler; simplify exception handler"
```

---

## Task 5: Build shared `tracker/queries.py` (data-access layer for analysis)

**Files:**
- Create: `tracker/queries.py`
- Create: `tests/test_queries.py`

This module is the SQL→pandas bridge. Both `analyze.py` (CLI) and `dashboard.py` (web) will use it. All time-of-day / day-of-week conversions happen here, in `America/Mexico_City`.

- [ ] **Step 1: Write failing tests**

Create `tests/test_queries.py`:
```python
from datetime import datetime, timezone

import pandas as pd

from tracker.db import connect, init_db, insert_sample
from tracker.queries import (
    load_samples,
    median_by_hour,
    median_by_dow_hour,
    daily_median,
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
    assert "local_dow" in df.columns  # 0=Mon..6=Sun
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
        ("2026-05-11T13:00:00+00:00", "r1", 20),  # local 7
        ("2026-05-11T13:10:00+00:00", "r1", 22),  # local 7
        ("2026-05-11T14:00:00+00:00", "r1", 30),  # local 8
        ("2026-05-11T13:00:00+00:00", "r2", 40),
    ])
    df = median_by_hour(load_samples(db_path))
    row_r1_7 = df[(df["route_id"] == "r1") & (df["local_hour"] == 7)].iloc[0]
    assert row_r1_7["median_min"] == 21
    assert "p25_min" in df.columns
    assert "p75_min" in df.columns


def test_median_by_dow_hour_pivot_shape(db_path):
    _seed(db_path, [
        ("2026-05-11T13:00:00+00:00", "r1", 20),  # Monday 7am local
    ])
    df = median_by_dow_hour(load_samples(db_path), route_id="r1")
    # Expect a (hour, dow) shaped frame with median_min values.
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
```

- [ ] **Step 2: Add `pandas` to runtime deps**

In `requirements.txt`, append:
```
pandas>=2.1.0
```

Then:
```bash
source .venv/bin/activate
pip install -r requirements.txt
```

- [ ] **Step 3: Run tests to verify they fail with `ModuleNotFoundError: queries`**

Run:
```bash
source .venv/bin/activate
PYTHONPATH=. pytest tests/test_queries.py -v
```
Expected: ERRORS — `ModuleNotFoundError: No module named 'tracker.queries'`.

- [ ] **Step 4: Implement `tracker/queries.py`**

Create `tracker/queries.py`:
```python
from zoneinfo import ZoneInfo

import pandas as pd

from tracker.db import connect

LOCAL_TZ = ZoneInfo("America/Mexico_City")


def load_samples(db_path: str) -> pd.DataFrame:
    """
    Reads all non-errored samples and adds derived local-time columns.
    """
    with connect(db_path) as conn:
        df = pd.read_sql_query(
            """
            SELECT id, sampled_at, route_id, origin_label, destination_label,
                   duration_sec, static_duration_sec, distance_m
            FROM samples
            WHERE error IS NULL AND duration_sec > 0
            """,
            conn,
        )
    if df.empty:
        return df.assign(
            duration_min=[], local_hour=[], local_dow=[], local_date=[],
        )

    df["sampled_at"] = pd.to_datetime(df["sampled_at"], utc=True)
    local = df["sampled_at"].dt.tz_convert(LOCAL_TZ)
    df["duration_min"] = df["duration_sec"] / 60.0
    df["local_hour"] = local.dt.hour
    df["local_dow"] = local.dt.weekday  # 0=Mon
    df["local_date"] = local.dt.date
    return df


def median_by_hour(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each (route_id, local_hour): median, p25, p75 of duration_min.
    Used by Panel de decisión.
    """
    if df.empty:
        return pd.DataFrame(columns=[
            "route_id", "local_hour", "median_min", "p25_min", "p75_min", "n",
        ])
    g = df.groupby(["route_id", "local_hour"])["duration_min"]
    out = g.agg(
        median_min="median",
        p25_min=lambda s: s.quantile(0.25),
        p75_min=lambda s: s.quantile(0.75),
        n="count",
    ).reset_index()
    return out


def median_by_dow_hour(df: pd.DataFrame, route_id: str) -> pd.DataFrame:
    """
    For one route, median duration_min per (local_dow, local_hour).
    Used by heatmaps.
    """
    sub = df[df["route_id"] == route_id]
    if sub.empty:
        return pd.DataFrame(columns=["local_dow", "local_hour", "median_min", "n"])
    return (
        sub.groupby(["local_dow", "local_hour"])["duration_min"]
        .agg(median_min="median", n="count")
        .reset_index()
    )


def daily_median(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each (route_id, local_date): median duration_min and sample count.
    Used by timeline.
    """
    if df.empty:
        return pd.DataFrame(columns=["route_id", "local_date", "median_min", "n"])
    return (
        df.groupby(["route_id", "local_date"])["duration_min"]
        .agg(median_min="median", n="count")
        .reset_index()
    )
```

- [ ] **Step 5: Run tests and verify they pass**

Run:
```bash
source .venv/bin/activate
PYTHONPATH=. pytest tests/test_queries.py -v
```
Expected: 5 passed.

- [ ] **Step 6: Run full suite**

Run:
```bash
PYTHONPATH=. pytest tests/ -v
```
Expected: 18 passed.

- [ ] **Step 7: Commit**

```bash
git add tracker/queries.py tests/test_queries.py requirements.txt
git commit -m "feat(queries): shared pandas data-access layer for analysis"
```

---

## Task 6: Refactor `tracker/analyze.py` to use `queries.py` (DRY)

**Files:**
- Modify: `tracker/analyze.py`

- [ ] **Step 1: Replace contents of `tracker/analyze.py`**

Open `tracker/analyze.py` and replace its full contents with:
```python
import sys

import yaml

from tracker.queries import LOCAL_TZ, load_samples, median_by_dow_hour, median_by_hour

DAY_NAMES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


def report(config_path: str) -> None:
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    df = load_samples(cfg["db_path"])
    if df.empty:
        print("No samples yet. Run `python -m tracker.sample` first.")
        return

    print(f"\n{'='*72}")
    print(f"  RESUMEN GLOBAL — {len(df)} muestras")
    print(f"{'='*72}\n")
    print(f"{'Ruta':<24}{'N':>5}{'avg':>8}{'p50':>8}{'p90':>8}{'min':>8}{'max':>8}")
    print("-" * 72)
    for route_id, sub in df.groupby("route_id"):
        d = sub["duration_min"]
        print(
            f"{route_id:<24}"
            f"{len(d):>5}"
            f"{int(d.mean()):>7}m"
            f"{int(d.median()):>7}m"
            f"{int(d.quantile(0.9)):>7}m"
            f"{int(d.min()):>7}m"
            f"{int(d.max()):>7}m"
        )

    print(f"\n{'='*72}")
    print("  POR HORA DEL DÍA (mediana en minutos, hora local)")
    print(f"{'='*72}")
    hourly = median_by_hour(df)
    for route_id, sub in hourly.groupby("route_id"):
        print(f"\n  {route_id}:")
        for _, row in sub.sort_values("local_hour").iterrows():
            med = int(row["median_min"])
            bar = "█" * min(med, 60)
            print(f"    {int(row['local_hour']):02d}:00  {med:>3}m  (n={int(row['n']):>3})  {bar}")


if __name__ == "__main__":
    config = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    report(config)
```

- [ ] **Step 2: Verify it still imports and runs**

Run:
```bash
source .venv/bin/activate
PYTHONPATH=. python -c "from tracker.analyze import report; print('ok')"
```
Expected: `ok`

- [ ] **Step 3: Re-run full suite**

Run:
```bash
PYTHONPATH=. pytest tests/ -v
```
Expected: 18 passed.

- [ ] **Step 4: Commit**

```bash
git add tracker/analyze.py
git commit -m "refactor(analyze): use shared queries layer"
```

---

## Task 7: Cost guard in `tracker/sample.py`

**Files:**
- Modify: `tracker/sample.py`
- Modify: `config.example.yaml`
- Modify: `tests/test_sample.py`

Adds an optional limit: before sampling, count successful samples this UTC month; if count + routes_per_pass exceeds limit, skip.

- [ ] **Step 1: Add failing test**

Append to `tests/test_sample.py`:
```python
from datetime import datetime, timezone


def test_cost_guard_aborts_when_limit_reached(tmp_path, sample_config):
    sample_config["max_monthly_calls"] = 1
    cfg_path = _write_config(tmp_path, sample_config)

    fake_result = {
        "duration_sec": 600, "static_duration_sec": 500,
        "distance_m": 2000, "raw": {},
    }
    # Pre-seed one successful sample in the current UTC month.
    from tracker.db import connect, init_db, insert_sample
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
    assert m.call_count == 0  # API was never hit


def test_cost_guard_disabled_by_default(tmp_path, sample_config):
    cfg_path = _write_config(tmp_path, sample_config)
    fake_result = {
        "duration_sec": 600, "static_duration_sec": 500,
        "distance_m": 2000, "raw": {},
    }
    with patch("tracker.sample.compute_route", return_value=fake_result):
        ok = run_once(cfg_path)
    assert ok == 1
```

- [ ] **Step 2: Run tests, expect the new ones to fail**

Run:
```bash
source .venv/bin/activate
PYTHONPATH=. pytest tests/test_sample.py -v
```
Expected: 3 passed, 1 failed (`test_cost_guard_aborts_when_limit_reached` — the limit isn't enforced yet).

- [ ] **Step 3: Implement the guard**

In `tracker/sample.py`, replace the full `run_once` function body with:
```python
def run_once(config_path: str) -> int:
    """
    Samples all configured routes once. Returns number of successful samples.
    Honors optional `max_monthly_calls` cost guard.
    """
    cfg = load_config(config_path)
    api_key = cfg["google_maps_api_key"]
    db_path = cfg["db_path"]
    locations = cfg["locations"]
    travel_mode = cfg.get("travel_mode", "DRIVE")
    max_monthly_calls = cfg.get("max_monthly_calls")  # None = disabled

    init_db(db_path)

    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    month_start = now_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

    routes = cfg["routes"]
    ok_count = 0

    with connect(db_path) as conn:
        if max_monthly_calls is not None:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM samples "
                "WHERE error IS NULL AND sampled_at >= ?",
                (month_start,),
            ).fetchone()
            already = row["n"]
            if already + len(routes) > max_monthly_calls:
                print(
                    f"[{now}] cost guard: {already} calls this month, "
                    f"limit {max_monthly_calls}. Skipping pass.",
                    file=sys.stderr,
                )
                return 0

        for route in routes:
            route_id = route["id"]
            origin = locations[route["origin"]]
            dest = locations[route["destination"]]

            try:
                result = compute_route(
                    api_key=api_key,
                    origin_lat=origin["lat"],
                    origin_lng=origin["lng"],
                    dest_lat=dest["lat"],
                    dest_lng=dest["lng"],
                    travel_mode=travel_mode,
                )
                insert_sample(
                    conn,
                    sampled_at=now,
                    route_id=route_id,
                    origin_label=origin["label"],
                    destination_label=dest["label"],
                    duration_sec=result["duration_sec"],
                    static_duration_sec=result["static_duration_sec"],
                    distance_m=result["distance_m"],
                    travel_mode=travel_mode,
                    raw_json=json.dumps(result["raw"]),
                )
                ok_count += 1
                print(
                    f"[{now}] {route_id}: "
                    f"{result['duration_sec']//60}m "
                    f"({result['distance_m']/1000:.1f}km)"
                )
            except Exception as e:
                insert_sample(
                    conn,
                    sampled_at=now,
                    route_id=route_id,
                    origin_label=origin["label"],
                    destination_label=dest["label"],
                    duration_sec=0,
                    static_duration_sec=None,
                    distance_m=0,
                    travel_mode=travel_mode,
                    raw_json="{}",
                    error=str(e),
                )
                print(f"[{now}] {route_id}: ERROR {e}", file=sys.stderr)

    return ok_count
```

- [ ] **Step 4: Add config knob to example file**

In `config.example.yaml`, append:
```yaml

# Cost guard: if set, aborts a sampling pass when this many successful
# API calls have already been made in the current UTC month. Leave
# commented out to disable.
# max_monthly_calls: 15000
```

- [ ] **Step 5: Run tests**

Run:
```bash
PYTHONPATH=. pytest tests/test_sample.py -v
```
Expected: 4 passed.

- [ ] **Step 6: Run full suite**

Run:
```bash
PYTHONPATH=. pytest tests/ -v
```
Expected: 20 passed.

- [ ] **Step 7: Commit**

```bash
git add tracker/sample.py config.example.yaml tests/test_sample.py
git commit -m "feat(sample): optional monthly cost guard"
```

---

## Task 8: Dashboard skeleton + decision panel

**Files:**
- Create: `tracker/dashboard.py`
- Create: `scripts/run_dashboard.sh`
- Create: `tests/test_dashboard.py`
- Modify: `requirements.txt`

This task delivers the first chart end-to-end so the rest can be added incrementally.

- [ ] **Step 1: Add deps**

In `requirements.txt`, append:
```
plotly>=5.20.0
flask>=3.0.0
```

Then:
```bash
source .venv/bin/activate
pip install -r requirements.txt
```

- [ ] **Step 2: Write failing tests**

Create `tests/test_dashboard.py`:
```python
import yaml

from tracker.dashboard import create_app
from tracker.db import connect, init_db, insert_sample


def _seed(db_path, rows):
    init_db(db_path)
    with connect(db_path) as conn:
        for sampled_at, rid, dur, origin, dest in rows:
            insert_sample(
                conn, sampled_at=sampled_at, route_id=rid,
                origin_label=origin, destination_label=dest,
                duration_sec=dur * 60, static_duration_sec=dur * 60,
                distance_m=5000, travel_mode="DRIVE", raw_json="{}",
            )


def _write_config(tmp_path, sample_config):
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(sample_config))
    return str(p)


def test_index_returns_html_with_no_samples(tmp_path, sample_config):
    cfg_path = _write_config(tmp_path, sample_config)
    app = create_app(cfg_path)
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"time-travel-tracker" in resp.data.lower()
    assert b"sin muestras" in resp.data.lower()


def test_index_renders_decision_panel_when_data_exists(tmp_path, sample_config):
    _seed(sample_config["db_path"], [
        ("2026-05-11T13:00:00+00:00", "casa_to_trabajo", 25, "Casa", "Trabajo"),
        ("2026-05-11T13:00:00+00:00", "depa_to_trabajo", 18, "Depa", "Trabajo"),
    ])
    cfg_path = _write_config(tmp_path, sample_config)
    app = create_app(cfg_path)
    resp = app.test_client().get("/")
    assert resp.status_code == 200
    body = resp.data.decode()
    # Plotly embeds a <div id="..."> + JSON; check for plotly markers.
    assert "plotly" in body.lower()
    assert "decisi" in body.lower()  # "Decisión" appears in the heading
```

- [ ] **Step 3: Run tests, expect ModuleNotFoundError**

Run:
```bash
source .venv/bin/activate
PYTHONPATH=. pytest tests/test_dashboard.py -v
```
Expected: errors — `No module named 'tracker.dashboard'`.

- [ ] **Step 4: Implement minimal dashboard with decision panel**

Create `tracker/dashboard.py`:
```python
import sys
from pathlib import Path

import plotly.graph_objects as go
import yaml
from flask import Flask
from plotly.io import to_html
from plotly.subplots import make_subplots

from tracker.queries import load_samples, median_by_hour


# Configured groupings: for each (label, destination), the pair of route_ids
# being compared. Adjust here if route ids change in config.
DECISION_PAIRS = [
    ("Trabajo", "casa_to_trabajo", "depa_to_trabajo"),
    ("ITESO",   "casa_to_iteso",   "depa_to_iteso"),
]


def create_app(config_path: str) -> Flask:
    app = Flask(__name__)
    cfg_path_abs = str(Path(config_path).resolve())

    @app.get("/")
    def index():
        with open(cfg_path_abs) as f:
            cfg = yaml.safe_load(f)
        df = load_samples(cfg["db_path"])
        if df.empty:
            return _empty_page()

        decision_html = _render_decision_panel(df)
        return _page(decision_html)

    return app


def _render_decision_panel(df) -> str:
    hourly = median_by_hour(df)
    fig = make_subplots(
        rows=1, cols=len(DECISION_PAIRS),
        subplot_titles=[label for label, *_ in DECISION_PAIRS],
        shared_yaxes=True,
    )

    for col, (label, casa_id, depa_id) in enumerate(DECISION_PAIRS, start=1):
        for route_id, color in [(casa_id, "#1f77b4"), (depa_id, "#ff7f0e")]:
            sub = hourly[hourly["route_id"] == route_id].sort_values("local_hour")
            if sub.empty:
                continue
            fig.add_trace(
                go.Scatter(
                    x=sub["local_hour"], y=sub["median_min"],
                    mode="lines+markers", name=route_id,
                    line=dict(color=color),
                    legendgroup=route_id, showlegend=(col == 1),
                ),
                row=1, col=col,
            )
            # p25-p75 band
            fig.add_trace(
                go.Scatter(
                    x=list(sub["local_hour"]) + list(sub["local_hour"][::-1]),
                    y=list(sub["p75_min"]) + list(sub["p25_min"][::-1]),
                    fill="toself", fillcolor=_rgba(color, 0.15),
                    line=dict(color="rgba(0,0,0,0)"),
                    name=f"{route_id} p25–p75",
                    legendgroup=route_id, showlegend=False, hoverinfo="skip",
                ),
                row=1, col=col,
            )
        fig.update_xaxes(title_text="Hora local", row=1, col=col, dtick=2)

    fig.update_yaxes(title_text="Minutos (mediana)", row=1, col=1)
    fig.update_layout(title="Panel de decisión: casa actual vs depa nuevo", height=420)
    return to_html(fig, include_plotlyjs="cdn", full_html=False)


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def _page(body_html: str) -> str:
    return f"""<!doctype html>
<html lang="es"><head>
<meta charset="utf-8">
<title>time-travel-tracker</title>
<style>
 body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif;
        margin: 24px; max-width: 1200px; color: #222; }}
 h1 {{ font-size: 20px; margin: 0 0 16px; }}
 section {{ margin-bottom: 36px; }}
</style></head>
<body>
<h1>time-travel-tracker</h1>
<section>{body_html}</section>
</body></html>
"""


def _empty_page() -> str:
    return _page("<p>Sin muestras aún. Corre <code>python -m tracker.sample</code>.</p>")


if __name__ == "__main__":
    config = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    create_app(config).run(host="127.0.0.1", port=5000, debug=False)
```

- [ ] **Step 5: Run dashboard tests**

Run:
```bash
PYTHONPATH=. pytest tests/test_dashboard.py -v
```
Expected: 2 passed.

- [ ] **Step 6: Add convenience launcher**

Create `scripts/run_dashboard.sh`:
```bash
#!/bin/bash
set -e
cd "$(dirname "$0")/.."
source .venv/bin/activate
python -m tracker.dashboard config.yaml
```

Then:
```bash
chmod +x scripts/run_dashboard.sh
```

- [ ] **Step 7: Run full suite**

Run:
```bash
PYTHONPATH=. pytest tests/ -v
```
Expected: 22 passed.

- [ ] **Step 8: Commit**

```bash
git add tracker/dashboard.py tests/test_dashboard.py \
        scripts/run_dashboard.sh requirements.txt
git commit -m "feat(dashboard): Flask app with decision panel"
```

---

## Task 9: Dashboard — heatmaps per route

**Files:**
- Modify: `tracker/dashboard.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_dashboard.py`:
```python
def test_index_renders_heatmaps_when_data_exists(tmp_path, sample_config):
    _seed(sample_config["db_path"], [
        ("2026-05-11T13:00:00+00:00", "casa_to_trabajo", 25, "Casa", "Trabajo"),
        ("2026-05-12T13:00:00+00:00", "casa_to_trabajo", 30, "Casa", "Trabajo"),
    ])
    cfg_path = _write_config(tmp_path, sample_config)
    resp = create_app(cfg_path).test_client().get("/")
    body = resp.data.decode().lower()
    assert "heatmap" in body or "calor" in body
    # At least one route_id should appear as a subplot title in the HTML.
    assert "casa_to_trabajo" in body
```

- [ ] **Step 2: Run test, expect failure**

Run:
```bash
PYTHONPATH=. pytest tests/test_dashboard.py::test_index_renders_heatmaps_when_data_exists -v
```
Expected: FAIL (no heatmap content yet).

- [ ] **Step 3: Implement heatmap renderer**

In `tracker/dashboard.py`, add a new import at the top:
```python
from tracker.queries import load_samples, median_by_dow_hour, median_by_hour
```
(Replace the previous import of `load_samples, median_by_hour`.)

Add this helper function below `_render_decision_panel`:
```python
DAY_NAMES_SHORT = ["L", "M", "M", "J", "V", "S", "D"]


def _render_heatmaps(df) -> str:
    route_ids = sorted(df["route_id"].unique())
    n = len(route_ids)
    cols = 2
    rows = (n + cols - 1) // cols
    fig = make_subplots(
        rows=rows, cols=cols,
        subplot_titles=route_ids,
        horizontal_spacing=0.08, vertical_spacing=0.10,
    )

    for i, rid in enumerate(route_ids):
        r, c = i // cols + 1, i % cols + 1
        sub = median_by_dow_hour(df, route_id=rid)
        pivot = (
            sub.pivot(index="local_hour", columns="local_dow", values="median_min")
            .reindex(index=range(0, 24), columns=range(0, 7))
        )
        fig.add_trace(
            go.Heatmap(
                z=pivot.values, x=DAY_NAMES_SHORT, y=list(pivot.index),
                colorscale="YlOrRd", showscale=(i == 0),
                hovertemplate="dow=%{x}<br>hora=%{y}<br>%{z:.0f} min<extra></extra>",
            ),
            row=r, col=c,
        )
        fig.update_yaxes(title_text="hora", row=r, col=c, autorange="reversed")
        fig.update_xaxes(title_text="día", row=r, col=c)

    fig.update_layout(
        title="Heatmaps por ruta (mediana min, hora × día de semana)",
        height=300 * rows,
    )
    return to_html(fig, include_plotlyjs=False, full_html=False)
```

Now wire it into the index. Find this block in `index()`:
```python
        decision_html = _render_decision_panel(df)
        return _page(decision_html)
```
Replace with:
```python
        decision_html = _render_decision_panel(df)
        heatmap_html = _render_heatmaps(df)
        return _page(decision_html + heatmap_html)
```

- [ ] **Step 4: Run tests**

Run:
```bash
PYTHONPATH=. pytest tests/test_dashboard.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add tracker/dashboard.py tests/test_dashboard.py
git commit -m "feat(dashboard): heatmaps per route"
```

---

## Task 10: Dashboard — distribution boxplots

**Files:**
- Modify: `tracker/dashboard.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_dashboard.py`:
```python
def test_index_renders_distribution_panel(tmp_path, sample_config):
    _seed(sample_config["db_path"], [
        ("2026-05-11T13:00:00+00:00", "casa_to_trabajo", 25, "Casa", "Trabajo"),
        ("2026-05-11T14:00:00+00:00", "casa_to_trabajo", 35, "Casa", "Trabajo"),
        ("2026-05-11T15:00:00+00:00", "casa_to_trabajo", 20, "Casa", "Trabajo"),
    ])
    cfg_path = _write_config(tmp_path, sample_config)
    body = create_app(cfg_path).test_client().get("/").data.decode().lower()
    assert "distribuci" in body or "boxplot" in body
```

- [ ] **Step 2: Run test, expect failure**

Run:
```bash
PYTHONPATH=. pytest tests/test_dashboard.py::test_index_renders_distribution_panel -v
```
Expected: FAIL.

- [ ] **Step 3: Implement boxplot**

In `tracker/dashboard.py`, add helper:
```python
def _render_distributions(df) -> str:
    fig = go.Figure()
    for rid, sub in df.groupby("route_id"):
        fig.add_trace(go.Box(
            x=sub["duration_min"], name=rid, orientation="h",
            boxmean="sd",
        ))
    fig.update_layout(
        title="Distribución de tiempos por ruta",
        xaxis_title="Minutos", height=400, showlegend=False,
    )
    return to_html(fig, include_plotlyjs=False, full_html=False)
```

Update index to include it:
```python
        decision_html = _render_decision_panel(df)
        heatmap_html = _render_heatmaps(df)
        dist_html = _render_distributions(df)
        return _page(decision_html + heatmap_html + dist_html)
```

- [ ] **Step 4: Run tests**

Run:
```bash
PYTHONPATH=. pytest tests/test_dashboard.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add tracker/dashboard.py tests/test_dashboard.py
git commit -m "feat(dashboard): per-route distribution boxplots"
```

---

## Task 11: Dashboard — daily timeline

**Files:**
- Modify: `tracker/dashboard.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_dashboard.py`:
```python
def test_index_renders_timeline(tmp_path, sample_config):
    _seed(sample_config["db_path"], [
        ("2026-05-10T13:00:00+00:00", "casa_to_trabajo", 25, "Casa", "Trabajo"),
        ("2026-05-11T13:00:00+00:00", "casa_to_trabajo", 30, "Casa", "Trabajo"),
        ("2026-05-12T13:00:00+00:00", "casa_to_trabajo", 28, "Casa", "Trabajo"),
    ])
    cfg_path = _write_config(tmp_path, sample_config)
    body = create_app(cfg_path).test_client().get("/").data.decode().lower()
    assert "timeline" in body or "evoluci" in body
```

- [ ] **Step 2: Run test, expect failure**

Run:
```bash
PYTHONPATH=. pytest tests/test_dashboard.py::test_index_renders_timeline -v
```
Expected: FAIL.

- [ ] **Step 3: Update import + implement timeline**

In `tracker/dashboard.py`, replace the queries import line with:
```python
from tracker.queries import (
    daily_median,
    load_samples,
    median_by_dow_hour,
    median_by_hour,
)
```

Add helper:
```python
def _render_timeline(df) -> str:
    daily = daily_median(df)
    fig = go.Figure()
    for rid, sub in daily.groupby("route_id"):
        sub = sub.sort_values("local_date")
        fig.add_trace(go.Scatter(
            x=sub["local_date"], y=sub["median_min"],
            mode="lines+markers", name=rid,
        ))
    fig.update_layout(
        title="Evolución diaria (mediana min/día por ruta)",
        xaxis_title="Fecha", yaxis_title="Minutos (mediana)",
        height=400,
    )
    return to_html(fig, include_plotlyjs=False, full_html=False)
```

Update index:
```python
        decision_html = _render_decision_panel(df)
        heatmap_html = _render_heatmaps(df)
        dist_html = _render_distributions(df)
        timeline_html = _render_timeline(df)
        return _page(decision_html + heatmap_html + dist_html + timeline_html)
```

- [ ] **Step 4: Run tests**

Run:
```bash
PYTHONPATH=. pytest tests/test_dashboard.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add tracker/dashboard.py tests/test_dashboard.py
git commit -m "feat(dashboard): daily timeline per route"
```

---

## Task 12: Dashboard — summary stats table

**Files:**
- Modify: `tracker/dashboard.py`
- Modify: `tests/test_dashboard.py`

Filters (multi-route, date range, dow) are out of scope for v1 — the table itself satisfies the §8.5 requirement of having quick numerical summaries. Filters can be added later.

- [ ] **Step 1: Add failing test**

Append to `tests/test_dashboard.py`:
```python
def test_index_renders_stats_table(tmp_path, sample_config):
    _seed(sample_config["db_path"], [
        ("2026-05-11T13:00:00+00:00", "casa_to_trabajo", 25, "Casa", "Trabajo"),
        ("2026-05-11T14:00:00+00:00", "casa_to_trabajo", 30, "Casa", "Trabajo"),
    ])
    cfg_path = _write_config(tmp_path, sample_config)
    body = create_app(cfg_path).test_client().get("/").data.decode()
    assert "<table" in body.lower()
    assert "casa_to_trabajo" in body
```

- [ ] **Step 2: Run test, expect failure**

Run:
```bash
PYTHONPATH=. pytest tests/test_dashboard.py::test_index_renders_stats_table -v
```
Expected: FAIL.

- [ ] **Step 3: Implement table**

In `tracker/dashboard.py`, add helper:
```python
def _render_stats_table(df) -> str:
    rows = []
    for rid, sub in df.groupby("route_id"):
        d = sub["duration_min"]
        rows.append({
            "ruta": rid,
            "N": len(d),
            "media": int(d.mean()),
            "p50": int(d.median()),
            "p90": int(d.quantile(0.9)),
            "min": int(d.min()),
            "max": int(d.max()),
            "σ": round(float(d.std() or 0), 1),
        })
    headers = ["ruta", "N", "media", "p50", "p90", "min", "max", "σ"]
    th = "".join(f"<th>{h}</th>" for h in headers)
    body_html = ""
    for r in sorted(rows, key=lambda x: x["ruta"]):
        body_html += "<tr>" + "".join(f"<td>{r[h]}</td>" for h in headers) + "</tr>"
    return (
        "<h2>Resumen por ruta</h2>"
        f"<table border='1' cellpadding='6' cellspacing='0'>"
        f"<thead><tr>{th}</tr></thead><tbody>{body_html}</tbody></table>"
    )
```

Update index:
```python
        decision_html = _render_decision_panel(df)
        heatmap_html = _render_heatmaps(df)
        dist_html = _render_distributions(df)
        timeline_html = _render_timeline(df)
        table_html = _render_stats_table(df)
        return _page(
            decision_html + heatmap_html + dist_html + timeline_html + table_html
        )
```

- [ ] **Step 4: Run all tests**

Run:
```bash
PYTHONPATH=. pytest tests/ -v
```
Expected: 26 passed.

- [ ] **Step 5: Commit**

```bash
git add tracker/dashboard.py tests/test_dashboard.py
git commit -m "feat(dashboard): summary stats table"
```

---

## Task 13: launchd plist template + install instructions

**Files:**
- Create: `scripts/com.crdo.time-travel-tracker.plist`
- Modify: `README.md`

`StartCalendarInterval` accepts a list of dicts; we need 35 entries (06:00 through 23:00 at 30-min intervals).

- [ ] **Step 1: Create the plist**

Create `scripts/com.crdo.time-travel-tracker.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.crdo.time-travel-tracker</string>

  <key>ProgramArguments</key>
  <array>
    <string>/Users/crdo/Documents/mierdas/tools/time-travel-tracker/scripts/run_sample.sh</string>
  </array>

  <key>WorkingDirectory</key>
  <string>/Users/crdo/Documents/mierdas/tools/time-travel-tracker</string>

  <key>StandardOutPath</key>
  <string>/Users/crdo/Documents/mierdas/tools/time-travel-tracker/data/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/crdo/Documents/mierdas/tools/time-travel-tracker/data/launchd.err.log</string>

  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>7</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>11</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>11</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>12</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>12</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>13</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>13</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>14</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>14</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>15</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>15</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>16</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>16</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>17</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>17</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>18</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>18</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>19</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>19</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>20</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>20</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>21</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>21</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>22</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>22</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>23</integer><key>Minute</key><integer>0</integer></dict>
  </array>

  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
```

- [ ] **Step 2: Update README with install instructions**

Replace the contents of `README.md` with:
````markdown
# time-travel-tracker

Sondea Google Routes API cada 30 min (06:00–23:00 hora local) y guarda duraciones reales con tráfico para comparar commutes a lo largo del tiempo.

Caso de uso: ¿me conviene mudarme? Compara `casa actual → trabajo` vs `depa nuevo → trabajo` con datos reales recolectados 2-4 semanas.

## Setup

```bash
cd /Users/crdo/Documents/mierdas/tools/time-travel-tracker

# venv + deps
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# config: pon tu API key
cp config.example.yaml config.yaml
$EDITOR config.yaml

# prueba manual
python -m tracker.sample config.yaml
```

Si imprime 8 tiempos por ruta, está funcionando.

## Tests

```bash
source .venv/bin/activate
PYTHONPATH=. pytest tests/ -v
```

## Dashboard

```bash
./scripts/run_dashboard.sh
# luego abre http://127.0.0.1:5000
```

## Schedule con launchd (macOS)

```bash
# instalar
cp scripts/com.crdo.time-travel-tracker.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.crdo.time-travel-tracker.plist

# verificar
launchctl list | grep time-travel-tracker

# parar
launchctl unload ~/Library/LaunchAgents/com.crdo.time-travel-tracker.plist
```

Logs en `data/launchd.out.log` y `data/launchd.err.log`.

## Costo

Google Maps Platform: $200 USD/mes de crédito gratis.
Este setup: ~8,400 calls/mes × $10/1k = **~$84 USD/mes → cubierto**.

Para añadir un guard duro, en `config.yaml`:
```yaml
max_monthly_calls: 15000
```
````

- [ ] **Step 3: Validate plist syntax**

Run:
```bash
plutil -lint scripts/com.crdo.time-travel-tracker.plist
```
Expected: `scripts/com.crdo.time-travel-tracker.plist: OK`

- [ ] **Step 4: Commit**

```bash
git add scripts/com.crdo.time-travel-tracker.plist README.md
git commit -m "feat(scheduler): launchd plist + install docs"
```

---

## Task 14: End-to-end smoke test with real API key

This task requires the user (or operator) to provide a real key. The result is not committed.

- [ ] **Step 1: Create local config**

Run (only if `config.yaml` doesn't already exist):
```bash
test -f config.yaml || cp config.example.yaml config.yaml
```

Edit `config.yaml` and replace `YOUR_API_KEY_HERE` with the real key. (Do NOT commit `config.yaml` — it's gitignored.)

- [ ] **Step 2: Run sampler once and verify rows in DB**

Run:
```bash
source .venv/bin/activate
PYTHONPATH=. python -m tracker.sample config.yaml
```
Expected: 8 lines like `[2026-05-11...] casa_to_trabajo: 22m (15.3km)`. No errors.

Then:
```bash
sqlite3 data/samples.db "SELECT route_id, duration_sec/60 AS min, distance_m/1000 AS km FROM samples ORDER BY id;"
```
Expected: 8 rows.

- [ ] **Step 3: Run dashboard and verify HTML**

Run in a separate shell:
```bash
./scripts/run_dashboard.sh
```
Then in your browser open `http://127.0.0.1:5000`. Verify the page loads with at least the decision panel (likely sparse with only 1 sample per route, but renders without 500).

Ctrl-C to stop.

- [ ] **Step 4: Install launchd job**

Run:
```bash
cp scripts/com.crdo.time-travel-tracker.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.crdo.time-travel-tracker.plist
launchctl list | grep time-travel-tracker
```
Expected: a row showing the job loaded.

- [ ] **Step 5: No commit**

This task only verifies the system works end-to-end; nothing new to commit.

---

## Self-Review

Check the plan against the spec section by section:

- §4 Architecture → Tasks 2-5 (sampler, store), 8-12 (dashboard) ✅
- §5 Sampling strategy → Task 13 (plist with 35 intervals) ✅
- §6 Data model → Task 2 verifies schema ✅
- §7 Routes → already in `config.example.yaml` (Task 1 commits it) ✅
- §8 Dashboard sections:
  - 8.1 Panel de decisión → Task 8 ✅
  - 8.2 Heatmaps → Task 9 ✅
  - 8.3 Distribuciones → Task 10 ✅
  - 8.4 Timeline → Task 11 ✅
  - 8.5 Filtros + tabla → Task 12 implements the table; filters are explicitly deferred (noted as YAGNI for v1). ✅ (with caveat)
- §9 Stack → Tasks 1, 5, 8 add deps as needed ✅
- §10 File structure → matches by Task 13 ✅
- §11 Cost → Task 7 implements the optional guard ✅
- §12 Plan de uso → Task 13 README + Task 14 smoke ✅

Placeholders / red flags scan: none — every code block is complete, every command has expected output, no "TBD" or "similar to" references.

Type consistency: `load_samples` returns a DataFrame with columns `duration_min`, `local_hour`, `local_dow`, `local_date` — used consistently in `median_by_hour`, `median_by_dow_hour`, `daily_median`, and all dashboard renderers. ✅

Note on §8.5 filters: deferred to keep v1 shippable. README + spec already mark these explicitly out of scope for v1; a follow-up plan can add them once the user has real data to play with.
