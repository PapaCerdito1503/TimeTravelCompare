import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from tracker.db import connect, init_db, insert_sample
from tracker.routes_api import compute_route


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


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
    max_monthly_calls = cfg.get("max_monthly_calls")

    init_db(db_path)

    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    month_start = now_dt.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    ).isoformat()

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


if __name__ == "__main__":
    config = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    config_path = str(Path(config).resolve())
    run_once(config_path)
