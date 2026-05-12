import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sampled_at TEXT NOT NULL,
    route_id TEXT NOT NULL,
    origin_label TEXT NOT NULL,
    destination_label TEXT NOT NULL,
    duration_sec INTEGER NOT NULL,
    static_duration_sec INTEGER,
    distance_m INTEGER NOT NULL,
    travel_mode TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_samples_route_time
    ON samples(route_id, sampled_at);

CREATE INDEX IF NOT EXISTS idx_samples_time
    ON samples(sampled_at);
"""


def init_db(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


@contextmanager
def connect(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def insert_sample(
    conn: sqlite3.Connection,
    *,
    sampled_at: str,
    route_id: str,
    origin_label: str,
    destination_label: str,
    duration_sec: int,
    static_duration_sec: int | None,
    distance_m: int,
    travel_mode: str,
    raw_json: str,
    error: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO samples (
            sampled_at, route_id, origin_label, destination_label,
            duration_sec, static_duration_sec, distance_m,
            travel_mode, raw_json, error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sampled_at,
            route_id,
            origin_label,
            destination_label,
            duration_sec,
            static_duration_sec,
            distance_m,
            travel_mode,
            raw_json,
            error,
        ),
    )
