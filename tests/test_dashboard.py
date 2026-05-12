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
    resp = app.test_client().get("/")
    assert resp.status_code == 200
    body = resp.data.decode().lower()
    assert "time-travel-tracker" in body
    assert "sin muestras" in body


def test_index_renders_all_panels_when_data_exists(tmp_path, sample_config):
    _seed(sample_config["db_path"], [
        ("2026-05-11T13:00:00+00:00", "casa_to_trabajo", 25, "Casa", "Trabajo"),
        ("2026-05-11T14:00:00+00:00", "casa_to_trabajo", 30, "Casa", "Trabajo"),
        ("2026-05-12T13:00:00+00:00", "casa_to_trabajo", 28, "Casa", "Trabajo"),
        ("2026-05-11T13:00:00+00:00", "depa_to_trabajo", 18, "Depa", "Trabajo"),
    ])
    cfg_path = _write_config(tmp_path, sample_config)
    resp = create_app(cfg_path).test_client().get("/")
    assert resp.status_code == 200
    body = resp.data.decode().lower()

    assert "plotly" in body
    assert "casa vs depa" in body
    assert "tiempo medio" in body
    assert "por hora del d" in body
    assert "evoluci" in body
    assert "estabilidad" in body
    assert "<table" in body
    assert "casa_to_trabajo" in body
    assert "depa_to_trabajo" in body
    assert "chip-row" in body
    assert "historial de muestreo" in body
    assert "pasadas" in body


def test_filter_chips_mark_active_range(tmp_path, sample_config):
    _seed(sample_config["db_path"], [
        ("2026-05-11T13:00:00+00:00", "casa_to_trabajo", 25, "Casa", "Trabajo"),
    ])
    cfg_path = _write_config(tmp_path, sample_config)
    body = create_app(cfg_path).test_client().get("/?range=last7").data.decode()
    # Active chip points to last7, others are plain chips.
    assert 'href="?range=last7"' in body
    assert 'chip chip-active' in body
    # All 7 range options present.
    for key in ["today", "yesterday", "last7", "last30", "this_month", "last_month", "all"]:
        assert f'href="?range={key}"' in body


def test_invalid_range_falls_back_to_all(tmp_path, sample_config):
    _seed(sample_config["db_path"], [
        ("2026-05-11T13:00:00+00:00", "casa_to_trabajo", 25, "Casa", "Trabajo"),
        ("2026-05-11T13:00:00+00:00", "depa_to_trabajo", 18, "Depa", "Trabajo"),
    ])
    cfg_path = _write_config(tmp_path, sample_config)
    resp = create_app(cfg_path).test_client().get("/?range=garbage")
    assert resp.status_code == 200
    # Falls back to "all"; the "all" chip is active.
    body = resp.data.decode()
    assert 'href="?range=all" >Toda la data</a>' in body.replace("\n", "") or \
           'class="chip chip-active" href="?range=all"' in body
    # Charts still render (means filtered df was not empty).
    assert "casa_to_trabajo" in body


def test_comparison_bars_show_grouped_casa_and_depa(tmp_path, sample_config):
    _seed(sample_config["db_path"], [
        ("2026-05-11T13:00:00+00:00", "casa_to_trabajo", 30, "Casa", "Trabajo"),
        ("2026-05-11T14:00:00+00:00", "casa_to_trabajo", 32, "Casa", "Trabajo"),
        ("2026-05-11T13:00:00+00:00", "depa_to_trabajo", 20, "Depa", "Trabajo"),
        ("2026-05-11T14:00:00+00:00", "depa_to_trabajo", 22, "Depa", "Trabajo"),
    ])
    cfg_path = _write_config(tmp_path, sample_config)
    body = create_app(cfg_path).test_client().get("/").data.decode()
    # Two Bar traces, one per origin.
    assert '"name":"desde casa"' in body
    assert '"name":"desde depa"' in body
    assert '"type":"bar"' in body
    # Bars are grouped (barmode="group") and laid out horizontally.
    assert '"barmode":"group"' in body
    assert '"orientation":"h"' in body
    # Direct labels on bars show median minutes.
    assert "31 min" in body  # casa median = (30+32)/2 = 31
    assert "21 min" in body  # depa median = (20+22)/2 = 21
