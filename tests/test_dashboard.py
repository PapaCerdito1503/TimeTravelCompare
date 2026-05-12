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
    assert "una fila = una sincronizaci" in body


def test_history_shows_one_row_per_sampled_at(tmp_path, sample_config):
    _seed(sample_config["db_path"], [
        ("2026-05-11T13:00:00+00:00", "casa_to_trabajo", 25, "Casa", "Trabajo"),
        ("2026-05-11T13:00:00+00:00", "depa_to_trabajo", 18, "Depa", "Trabajo"),
        ("2026-05-11T13:30:00+00:00", "casa_to_trabajo", 27, "Casa", "Trabajo"),
        ("2026-05-11T13:30:00+00:00", "depa_to_trabajo", 19, "Depa", "Trabajo"),
        ("2026-05-11T14:00:00+00:00", "casa_to_trabajo", 30, "Casa", "Trabajo"),
    ])
    cfg_path = _write_config(tmp_path, sample_config)
    body = create_app(cfg_path).test_client().get("/").data.decode()
    # 3 unique sampled_at values → 3 history rows containing those exact local times
    assert "07:00:00" in body  # 13:00 UTC = 07:00 MX local
    assert "07:30:00" in body
    assert "08:00:00" in body
    # Per-row N rutas column shows X/Y
    assert "2/2" in body
    assert "1/1" in body


def test_filter_chips_mark_active_range(tmp_path, sample_config):
    _seed(sample_config["db_path"], [
        ("2026-05-11T13:00:00+00:00", "casa_to_trabajo", 25, "Casa", "Trabajo"),
    ])
    cfg_path = _write_config(tmp_path, sample_config)
    body = create_app(cfg_path).test_client().get("/?range=last7").data.decode()
    assert 'href="?range=last7"' in body
    assert 'chip chip-active' in body
    for key in ["today", "yesterday", "last7", "last30", "this_month", "last_month", "all"]:
        assert f'href="?range={key}' in body


def test_invalid_range_falls_back_to_all(tmp_path, sample_config):
    _seed(sample_config["db_path"], [
        ("2026-05-11T13:00:00+00:00", "casa_to_trabajo", 25, "Casa", "Trabajo"),
        ("2026-05-11T13:00:00+00:00", "depa_to_trabajo", 18, "Depa", "Trabajo"),
    ])
    cfg_path = _write_config(tmp_path, sample_config)
    resp = create_app(cfg_path).test_client().get("/?range=garbage")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert 'class="chip chip-active" href="?range=all"' in body
    assert "casa_to_trabajo" in body


def test_custom_from_to_filters_dates(tmp_path, sample_config):
    _seed(sample_config["db_path"], [
        ("2026-05-10T13:00:00+00:00", "casa_to_trabajo", 25, "Casa", "Trabajo"),
        ("2026-05-11T13:00:00+00:00", "casa_to_trabajo", 30, "Casa", "Trabajo"),
        ("2026-05-12T13:00:00+00:00", "casa_to_trabajo", 28, "Casa", "Trabajo"),
        ("2026-05-13T13:00:00+00:00", "casa_to_trabajo", 27, "Casa", "Trabajo"),
    ])
    cfg_path = _write_config(tmp_path, sample_config)
    body = create_app(cfg_path).test_client().get(
        "/?from=2026-05-11&to=2026-05-12"
    ).data.decode()
    assert "fechas <b>2026-05-11</b> a <b>2026-05-12</b>" in body
    # 2 days × 1 route = 2 muestras kept
    assert "2 muestras" in body


def test_hour_filter_narrows_data(tmp_path, sample_config):
    _seed(sample_config["db_path"], [
        ("2026-05-11T12:00:00+00:00", "casa_to_trabajo", 25, "Casa", "Trabajo"),  # 06:00 local
        ("2026-05-11T13:00:00+00:00", "casa_to_trabajo", 30, "Casa", "Trabajo"),  # 07:00
        ("2026-05-11T15:00:00+00:00", "casa_to_trabajo", 28, "Casa", "Trabajo"),  # 09:00
        ("2026-05-11T20:00:00+00:00", "casa_to_trabajo", 35, "Casa", "Trabajo"),  # 14:00
    ])
    cfg_path = _write_config(tmp_path, sample_config)
    body = create_app(cfg_path).test_client().get(
        "/?hour_from=6&hour_to=9"
    ).data.decode()
    # hours 6,7,9 → 3 muestras kept; 14:00 dropped
    assert "hora <b>6:00–9:59</b>" in body
    assert "3 muestras" in body


def test_chip_link_preserves_hour_filter(tmp_path, sample_config):
    _seed(sample_config["db_path"], [
        ("2026-05-11T13:00:00+00:00", "casa_to_trabajo", 25, "Casa", "Trabajo"),
    ])
    cfg_path = _write_config(tmp_path, sample_config)
    body = create_app(cfg_path).test_client().get(
        "/?range=last7&hour_from=6&hour_to=10"
    ).data.decode()
    # Each chip URL includes the current hour filter
    assert "?range=today&amp;hour_from=6&amp;hour_to=10" in body or \
           "?range=today&hour_from=6&hour_to=10" in body
    assert "?range=all&amp;hour_from=6&amp;hour_to=10" in body or \
           "?range=all&hour_from=6&hour_to=10" in body


def test_form_inputs_show_current_filter_values(tmp_path, sample_config):
    _seed(sample_config["db_path"], [
        ("2026-05-11T13:00:00+00:00", "casa_to_trabajo", 25, "Casa", "Trabajo"),
    ])
    cfg_path = _write_config(tmp_path, sample_config)
    body = create_app(cfg_path).test_client().get(
        "/?from=2026-05-10&to=2026-05-12&hour_from=7&hour_to=9"
    ).data.decode()
    assert 'name="from" value="2026-05-10"' in body
    assert 'name="to" value="2026-05-12"' in body
    assert 'name="hour_from" value="7"' in body
    assert 'name="hour_to" value="9"' in body


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
