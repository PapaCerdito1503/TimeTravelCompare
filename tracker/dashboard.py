import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import yaml
from flask import Flask
from plotly.io import to_html
from plotly.subplots import make_subplots

from tracker.db import init_db
from tracker.queries import (
    LOCAL_TZ,
    load_samples,
    median_by_dow_hour,
)

DECISION_PAIRS = [
    ("→ Trabajo (ida)",      "casa_to_trabajo", "depa_to_trabajo"),
    ("Trabajo → (vuelta)",   "trabajo_to_casa", "trabajo_to_depa"),
    ("→ ITESO (ida)",        "casa_to_iteso",   "depa_to_iteso"),
    ("ITESO → (vuelta)",     "iteso_to_casa",   "iteso_to_depa"),
]

DAY_NAMES_SHORT = ["L", "M", "X", "J", "V", "S", "D"]


def create_app(config_path: str) -> Flask:
    app = Flask(__name__)
    cfg_path_abs = str(Path(config_path).resolve())
    with open(cfg_path_abs) as f:
        init_db(yaml.safe_load(f)["db_path"])

    @app.get("/")
    def index():
        with open(cfg_path_abs) as f:
            cfg = yaml.safe_load(f)
        df = load_samples(cfg["db_path"])
        if df.empty:
            return _empty_page()

        sections = [
            "<h2>Casa vs depa · tiempo medio por dirección</h2>",
            _render_comparison_bars(df),
            "<h2>Por hora del día</h2>",
            _render_hour_overlay(df),
            "<h2>Por día · mediana y rango (mín–máx)</h2>",
            _render_daily_range(df),
            "<h2>Estabilidad · ¿quién varía menos?</h2>",
            _render_stability_bars(df),
            "<h2>Detalle por ruta</h2>",
            _render_abs_heatmaps(df),
            _render_stats_table(df),
        ]
        return _page("".join(sections))

    return app


# --- Distribution histograms ---------------------------------------------

COLOR_CASA = "#3b82f6"   # blue
COLOR_DEPA = "#f97316"   # orange


def _render_comparison_bars(df: pd.DataFrame) -> str:
    pairs = DECISION_PAIRS

    labels, casa_meds, depa_meds, casa_n, depa_n = [], [], [], [], []
    for label, casa_id, depa_id in pairs:
        casa = df[df["route_id"] == casa_id]["duration_min"]
        depa = df[df["route_id"] == depa_id]["duration_min"]
        if casa.empty and depa.empty:
            continue
        labels.append(label)
        casa_meds.append(float(casa.median()) if not casa.empty else 0.0)
        depa_meds.append(float(depa.median()) if not depa.empty else 0.0)
        casa_n.append(len(casa))
        depa_n.append(len(depa))

    if not labels:
        return ""

    casa_texts = [
        f"{v:.0f} min" if n > 0 else "—"
        for v, n in zip(casa_meds, casa_n)
    ]
    depa_texts = [
        f"{v:.0f} min" if n > 0 else "—"
        for v, n in zip(depa_meds, depa_n)
    ]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=labels, x=casa_meds, name="desde casa",
        orientation="h", marker_color=COLOR_CASA,
        text=casa_texts, textposition="outside", textfont=dict(size=13),
        customdata=casa_n,
        hovertemplate="<b>desde casa</b>: %{x:.1f} min (n=%{customdata})<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        y=labels, x=depa_meds, name="desde depa",
        orientation="h", marker_color=COLOR_DEPA,
        text=depa_texts, textposition="outside", textfont=dict(size=13),
        customdata=depa_n,
        hovertemplate="<b>desde depa</b>: %{x:.1f} min (n=%{customdata})<extra></extra>",
    ))

    x_max = max(casa_meds + depa_meds) * 1.32
    annotations = []
    for i, label in enumerate(labels):
        if casa_n[i] == 0 or depa_n[i] == 0:
            continue
        delta = casa_meds[i] - depa_meds[i]
        sign = "+" if delta >= 0 else ""
        color = "#15803d" if delta > 0 else "#b91c1c" if delta < 0 else "#6b7280"
        annotations.append(dict(
            x=x_max * 0.97, y=label,
            text=f"<b>Δ {sign}{delta:.0f} min</b>",
            showarrow=False,
            font=dict(size=14, color=color),
            xanchor="right",
        ))

    fig.update_layout(
        title=(
            "<b>Tiempo medio por dirección</b>  "
            "<span style='color:#666;font-size:13px;font-weight:400'>"
            "(barra = mediana en minutos)</span>"
        ),
        xaxis=dict(title="Minutos (mediana)", range=[0, x_max], gridcolor="#eee"),
        yaxis=dict(autorange="reversed", tickfont=dict(size=13)),
        barmode="group",
        bargap=0.30,
        bargroupgap=0.15,
        height=110 * len(labels) + 140,
        margin=dict(t=90, b=80, l=160, r=40),
        annotations=annotations,
        legend=dict(orientation="h", y=-0.18, x=0.5, xanchor="center"),
        plot_bgcolor="white",
    )
    return to_html(fig, include_plotlyjs="cdn", full_html=False)


# --- Detail section ------------------------------------------------------

def _render_hour_overlay(df: pd.DataFrame) -> str:
    if df.empty:
        return ""

    df = df.copy()
    local = df["sampled_at"].dt.tz_convert(LOCAL_TZ)
    df["hour_decimal"] = local.dt.hour + local.dt.minute / 60.0

    pairs = DECISION_PAIRS
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=[label for label, *_ in pairs],
        horizontal_spacing=0.08, vertical_spacing=0.20,
        shared_yaxes=True,
    )

    legend_shown = {"desde casa": False, "desde depa": False}

    for i, (label, casa_id, depa_id) in enumerate(pairs):
        r, c = i // 2 + 1, i % 2 + 1
        for route_id, color, name in [
            (casa_id, COLOR_CASA, "desde casa"),
            (depa_id, COLOR_DEPA, "desde depa"),
        ]:
            sub = df[df["route_id"] == route_id]
            if sub.empty:
                continue
            for date, day_sub in sub.groupby("local_date"):
                day_sub = day_sub.sort_values("hour_decimal")
                show = not legend_shown[name]
                legend_shown[name] = True
                fig.add_trace(
                    go.Scatter(
                        x=day_sub["hour_decimal"],
                        y=day_sub["duration_min"],
                        mode="lines+markers",
                        line=dict(color=color, width=1.5),
                        marker=dict(size=5),
                        opacity=0.55,
                        legendgroup=name,
                        showlegend=show,
                        name=name,
                        customdata=[str(date)] * len(day_sub),
                        hovertemplate=(
                            f"<b>{name}</b><br>"
                            "fecha=%{customdata}<br>"
                            "hora=%{x:.2f}<br>"
                            "%{y:.1f} min<extra></extra>"
                        ),
                    ),
                    row=r, col=c,
                )
        fig.update_xaxes(
            title_text="Hora local", row=r, col=c,
            dtick=2, range=[5.5, 23.5],
        )

    fig.update_yaxes(title_text="Minutos", row=1, col=1)
    fig.update_yaxes(title_text="Minutos", row=2, col=1)
    fig.update_layout(
        title=(
            "<b>Por hora del día</b>  "
            "<span style='color:#666;font-size:13px;font-weight:400'>"
            "una línea por día y por ruta · cada punto = una muestra real</span>"
        ),
        height=640,
        margin=dict(t=80, b=60),
        legend=dict(orientation="h", y=-0.06, x=0.5, xanchor="center"),
        plot_bgcolor="white",
    )
    return to_html(fig, include_plotlyjs=False, full_html=False)


def _render_daily_range(df: pd.DataFrame) -> str:
    daily = (
        df.groupby(["route_id", "local_date"])["duration_min"]
        .agg(median="median", min="min", max="max", n="count")
        .reset_index()
        .sort_values(["route_id", "local_date"])
    )
    if daily.empty:
        return ""

    pairs = DECISION_PAIRS
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=[label for label, *_ in pairs],
        horizontal_spacing=0.08, vertical_spacing=0.20,
        shared_yaxes=True,
    )

    for i, (label, casa_id, depa_id) in enumerate(pairs):
        r, c = i // 2 + 1, i % 2 + 1
        for rid, color, name in [
            (casa_id, COLOR_CASA, "desde casa"),
            (depa_id, COLOR_DEPA, "desde depa"),
        ]:
            sub = daily[daily["route_id"] == rid]
            if sub.empty:
                continue
            x = list(sub["local_date"])
            fig.add_trace(
                go.Scatter(
                    x=x + x[::-1],
                    y=list(sub["max"]) + list(sub["min"])[::-1],
                    fill="toself", fillcolor=_rgba_hex(color, 0.15),
                    line=dict(width=0), hoverinfo="skip",
                    showlegend=False,
                ),
                row=r, col=c,
            )
            fig.add_trace(
                go.Scatter(
                    x=x, y=sub["median"],
                    mode="lines+markers", name=name,
                    line=dict(color=color, width=2),
                    marker=dict(size=6),
                    legendgroup=name, showlegend=(i == 0),
                    customdata=list(zip(sub["min"], sub["max"], sub["n"])),
                    hovertemplate=(
                        f"{name}<br>"
                        "fecha=%{x}<br>"
                        "mediana=%{y:.1f} min<br>"
                        "rango=%{customdata[0]:.0f}–%{customdata[1]:.0f} min "
                        "(n=%{customdata[2]})<extra></extra>"
                    ),
                ),
                row=r, col=c,
            )

    fig.update_yaxes(title_text="Minutos", row=1, col=1)
    fig.update_yaxes(title_text="Minutos", row=2, col=1)
    fig.update_layout(
        title=(
            "<b>Evolución diaria</b>  "
            "<span style='color:#666;font-size:13px;font-weight:400'>"
            "línea = mediana · banda = mín–máx del día</span>"
        ),
        height=620,
        margin=dict(t=80, b=60),
        legend=dict(orientation="h", y=-0.06, x=0.5, xanchor="center"),
        plot_bgcolor="white",
    )
    return to_html(fig, include_plotlyjs=False, full_html=False)


def _render_stability_bars(df: pd.DataFrame) -> str:
    pairs = DECISION_PAIRS
    labels, casa_s, depa_s = [], [], []
    for label, casa_id, depa_id in pairs:
        casa = df[df["route_id"] == casa_id]["duration_min"]
        depa = df[df["route_id"] == depa_id]["duration_min"]
        if casa.empty and depa.empty:
            continue
        labels.append(label)
        casa_s.append(float(casa.std() or 0))
        depa_s.append(float(depa.std() or 0))

    if not labels:
        return ""

    casa_texts = [f"σ={s:.1f}" if s > 0 else "—" for s in casa_s]
    depa_texts = [f"σ={s:.1f}" if s > 0 else "—" for s in depa_s]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=labels, x=casa_s, name="desde casa",
        orientation="h", marker_color=COLOR_CASA,
        text=casa_texts, textposition="outside", textfont=dict(size=13),
        hovertemplate="casa: σ=%{x:.2f} min<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        y=labels, x=depa_s, name="desde depa",
        orientation="h", marker_color=COLOR_DEPA,
        text=depa_texts, textposition="outside", textfont=dict(size=13),
        hovertemplate="depa: σ=%{x:.2f} min<extra></extra>",
    ))

    x_max = (max(casa_s + depa_s) or 1) * 1.30

    fig.update_layout(
        title=(
            "<b>Desviación estándar</b>  "
            "<span style='color:#666;font-size:13px;font-weight:400'>"
            "barra más corta = más estable y predecible</span>"
        ),
        xaxis=dict(title="σ (min)", range=[0, x_max], gridcolor="#eee"),
        yaxis=dict(autorange="reversed", tickfont=dict(size=13)),
        barmode="group",
        bargap=0.30,
        bargroupgap=0.15,
        height=110 * len(labels) + 140,
        margin=dict(t=80, b=80, l=160, r=40),
        legend=dict(orientation="h", y=-0.18, x=0.5, xanchor="center"),
        plot_bgcolor="white",
    )
    return to_html(fig, include_plotlyjs=False, full_html=False)


def _rgba_hex(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def _render_abs_heatmaps(df: pd.DataFrame) -> str:
    route_ids = sorted(df["route_id"].unique())
    cols = 2
    rows = (len(route_ids) + cols - 1) // cols

    z_min = float(df["duration_min"].min())
    z_max = float(df["duration_min"].max())

    fig = make_subplots(
        rows=rows, cols=cols,
        subplot_titles=route_ids,
        horizontal_spacing=0.10, vertical_spacing=0.10,
    )
    for i, rid in enumerate(route_ids):
        r, c = i // cols + 1, i % cols + 1
        sub = median_by_dow_hour(df, route_id=rid)
        pivot = (
            sub.pivot(index="local_hour", columns="local_dow", values="median_min")
            .reindex(index=range(24), columns=range(7))
        )
        fig.add_trace(
            go.Heatmap(
                z=pivot.values, x=DAY_NAMES_SHORT, y=list(pivot.index),
                colorscale="YlOrRd",
                zmin=z_min, zmax=z_max,
                showscale=(i == 0),
                hovertemplate="día=%{x}<br>hora=%{y}:00<br>%{z:.0f} min<extra></extra>",
            ),
            row=r, col=c,
        )
        fig.update_yaxes(title_text="hora", row=r, col=c, autorange="reversed")
        fig.update_xaxes(title_text="día", row=r, col=c)

    fig.update_layout(
        title="<b>Tiempos absolutos</b> por ruta (mediana min, hora × día)",
        height=300 * rows,
    )
    return to_html(fig, include_plotlyjs=False, full_html=False)


def _render_stats_table(df: pd.DataFrame) -> str:
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
    for row in sorted(rows, key=lambda x: x["ruta"]):
        body_html += "<tr>" + "".join(f"<td>{row[h]}</td>" for h in headers) + "</tr>"
    return (
        "<h3>Resumen estadístico por ruta</h3>"
        "<table class='stats-table'>"
        f"<thead><tr>{th}</tr></thead><tbody>{body_html}</tbody></table>"
    )


# --- Page chrome ---------------------------------------------------------

def _page(body_html: str) -> str:
    return f"""<!doctype html>
<html lang="es"><head>
<meta charset="utf-8">
<title>time-travel-tracker</title>
<style>
 body {{
   font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", sans-serif;
   margin: 24px auto; max-width: 1200px; color: #222; padding: 0 16px;
   background: #fafafa;
 }}
 h1 {{ font-size: 22px; margin: 0 0 8px; }}
 h2 {{ font-size: 18px; margin: 32px 0 12px; color: #222;
       border-bottom: 1px solid #e0e0e0; padding-bottom: 6px; }}
 h3 {{ font-size: 14px; margin: 24px 0 8px; color: #555;
       text-transform: uppercase; letter-spacing: 0.04em; }}
 .subtitle {{ color: #666; font-size: 13px; margin-bottom: 24px; }}

 .stats-table {{
   border-collapse: collapse;
   font-size: 13px;
   font-variant-numeric: tabular-nums;
   width: 100%;
   max-width: 720px;
   background: white;
 }}
 .stats-table th, .stats-table td {{
   border: 1px solid #e3e3e3; padding: 6px 10px;
 }}
 .stats-table th {{ background: #f4f4f4; text-align: left; font-weight: 600; }}
 .stats-table td {{ text-align: right; }}
 .stats-table td:first-child {{
   text-align: left; font-family: ui-monospace, monospace; font-size: 12px;
 }}
</style></head>
<body>
<h1>time-travel-tracker</h1>
<p class="subtitle">¿Casa actual o depa nuevo? · datos reales con tráfico de Google Routes</p>
{body_html}
</body></html>
"""


def _empty_page() -> str:
    return _page(
        "<p>Sin muestras aún. Corre <code>python -m tracker.sample config.yaml</code>"
        " para hacer la primera muestra.</p>"
    )


if __name__ == "__main__":
    config = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    create_app(config).run(host="127.0.0.1", port=5000, debug=False)
