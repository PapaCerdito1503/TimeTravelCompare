import sys

import yaml

from tracker.queries import load_samples, median_by_hour


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
