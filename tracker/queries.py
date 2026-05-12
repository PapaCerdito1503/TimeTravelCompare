from zoneinfo import ZoneInfo

import pandas as pd

from tracker.db import connect

LOCAL_TZ = ZoneInfo("America/Mexico_City")


def load_samples(db_path: str) -> pd.DataFrame:
    """
    Reads all non-errored samples and adds derived local-time columns:
    duration_min, local_hour, local_dow (0=Mon), local_date.
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
    df["local_dow"] = local.dt.weekday
    df["local_date"] = local.dt.date
    return df


def median_by_hour(df: pd.DataFrame) -> pd.DataFrame:
    """For each (route_id, local_hour): median, p25, p75, n."""
    if df.empty:
        return pd.DataFrame(columns=[
            "route_id", "local_hour", "median_min", "p25_min", "p75_min", "n",
        ])
    g = df.groupby(["route_id", "local_hour"])["duration_min"]
    return g.agg(
        median_min="median",
        p25_min=lambda s: s.quantile(0.25),
        p75_min=lambda s: s.quantile(0.75),
        n="count",
    ).reset_index()


def median_by_dow_hour(df: pd.DataFrame, route_id: str) -> pd.DataFrame:
    """For one route, median duration_min per (local_dow, local_hour)."""
    sub = df[df["route_id"] == route_id]
    if sub.empty:
        return pd.DataFrame(columns=["local_dow", "local_hour", "median_min", "n"])
    return (
        sub.groupby(["local_dow", "local_hour"])["duration_min"]
        .agg(median_min="median", n="count")
        .reset_index()
    )


def daily_median(df: pd.DataFrame) -> pd.DataFrame:
    """For each (route_id, local_date): median duration_min and sample count."""
    if df.empty:
        return pd.DataFrame(columns=["route_id", "local_date", "median_min", "n"])
    return (
        df.groupby(["route_id", "local_date"])["duration_min"]
        .agg(median_min="median", n="count")
        .reset_index()
    )


def pair_hourly_savings(
    df: pd.DataFrame, casa_id: str, depa_id: str
) -> pd.DataFrame:
    """
    For one casa/depa pair, returns savings (= casa - depa) by local_hour.
    Positive savings = depa is faster = good for moving.
    Columns: local_hour, casa_min, depa_min, savings_min, n_casa, n_depa.
    """
    hourly = median_by_hour(df)
    casa = hourly[hourly["route_id"] == casa_id].set_index("local_hour")
    depa = hourly[hourly["route_id"] == depa_id].set_index("local_hour")
    common = casa.index.intersection(depa.index)
    if len(common) == 0:
        return pd.DataFrame(columns=[
            "local_hour", "casa_min", "depa_min", "savings_min", "n_casa", "n_depa",
        ])
    out = pd.DataFrame({
        "local_hour": common,
        "casa_min": casa.loc[common, "median_min"].values,
        "depa_min": depa.loc[common, "median_min"].values,
        "n_casa": casa.loc[common, "n"].values,
        "n_depa": depa.loc[common, "n"].values,
    })
    out["savings_min"] = out["casa_min"] - out["depa_min"]
    return out.sort_values("local_hour").reset_index(drop=True)


def pair_dow_hour_savings(
    df: pd.DataFrame, casa_id: str, depa_id: str
) -> pd.DataFrame:
    """
    For one casa/depa pair, returns a 24×7 pivot of savings (casa - depa)
    indexed by local_hour (rows) and local_dow (cols).
    """
    casa_p = (
        median_by_dow_hour(df, route_id=casa_id)
        .pivot(index="local_hour", columns="local_dow", values="median_min")
        .reindex(index=range(24), columns=range(7))
    )
    depa_p = (
        median_by_dow_hour(df, route_id=depa_id)
        .pivot(index="local_hour", columns="local_dow", values="median_min")
        .reindex(index=range(24), columns=range(7))
    )
    return casa_p - depa_p
