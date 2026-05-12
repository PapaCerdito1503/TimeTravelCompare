# time-travel-tracker — Diseño

**Fecha:** 2026-05-11
**Autor:** crdo
**Estado:** Aprobado para implementación

## 1. Contexto y motivación

El usuario evalúa mudarse de su casa actual (Parque Las Lomas, Guadalajara) a un depa nuevo (Lomaira). La decisión depende fuertemente del tiempo de traslado a dos destinos: **trabajo (WeWork)** e **ITESO (escuela)**.

No hay horarios fijos aún (escuela y trabajo varían), por lo que la herramienta debe muestrear *ampliamente* a lo largo del día durante varias semanas y permitir explorar los datos visualmente para responder preguntas como:

- ¿En qué horario me conviene más cada origen?
- ¿La diferencia de tiempo justifica la mudanza?
- ¿Hay franjas catastróficas que debería evitar?

## 2. Objetivos

1. Recolectar tiempos de traslado **reales con tráfico** entre 4 puntos (2 orígenes × 2 destinos, ida y vuelta = 8 rutas) durante al menos 2-3 semanas.
2. Almacenar muestras crudas para re-análisis posterior.
3. Servir un **dashboard web local** que responda en segundos: *¿qué tan diferente es la vida desde cada origen?*

## 3. No-objetivos

- No es un sistema de producción multi-usuario.
- No predice tráfico ni hace ML.
- No considera transporte público o bici (solo `DRIVE`).
- No replica el histórico real de Google (no existe API pública para eso); construye su propio histórico hacia adelante.

## 4. Arquitectura

```
┌─────────────────┐    ┌──────────────────┐    ┌──────────────┐
│  launchd        │───▶│  Sampler         │───▶│  SQLite      │
│  StartCalendar  │    │  tracker/sample  │    │  samples.db  │
│  06:00..23:00   │    └──────────────────┘    └──────┬───────┘
│  cada 30 min    │                                   │
└─────────────────┘                                   ▼
                       ┌──────────────────┐    ┌──────────────┐
                       │  Browser         │◀───│  Flask app   │
                       │  localhost:5000  │    │  + Plotly    │
                       └──────────────────┘    └──────────────┘
```

Tres componentes, cada uno con responsabilidad única y borde claro:

- **Sampler** (`tracker/sample.py`): lee config, consulta Routes API, inserta filas. No sabe nada de visualización.
- **Storage** (`tracker/db.py`, `data/samples.db`): schema fijo, helpers de inserción/lectura. No sabe nada de la API ni del dashboard.
- **Dashboard** (`tracker/dashboard.py`): solo lee SQLite, renderiza HTML. No sabe nada de la API.

## 5. Estrategia de muestreo

| Parámetro | Valor |
|---|---|
| Cadence | Cada 30 minutos |
| Ventana diaria | 06:00 – 23:00 hora local (America/Mexico_City) |
| Días | Todos los de la semana |
| Disparos/día | 35 |
| Rutas por disparo | 8 |
| Llamadas/día | 280 |
| Llamadas/mes (~30 días) | ~8,400 |
| Modo | `DRIVE` con `TRAFFIC_AWARE_OPTIMAL` |

**Robustez:** un fallo en una ruta no interrumpe las otras. Errores se persisten en la columna `error` para revisión.

## 6. Modelo de datos

Tabla única `samples`, una fila por (ruta, instante de muestreo):

```sql
CREATE TABLE samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sampled_at TEXT NOT NULL,           -- ISO 8601 UTC
    route_id TEXT NOT NULL,             -- ej "casa_to_trabajo"
    origin_label TEXT NOT NULL,
    destination_label TEXT NOT NULL,
    duration_sec INTEGER NOT NULL,      -- con tráfico
    static_duration_sec INTEGER,        -- sin tráfico (baseline)
    distance_m INTEGER NOT NULL,
    travel_mode TEXT NOT NULL,
    raw_json TEXT NOT NULL,             -- respuesta cruda para re-análisis
    error TEXT                          -- NULL si OK
);
CREATE INDEX idx_samples_route_time ON samples(route_id, sampled_at);
CREATE INDEX idx_samples_time ON samples(sampled_at);
```

Conversión de timestamp a hora local y día de semana se hace en consulta (no se persiste), para evitar problemas de DST y dejar la fuente de verdad en UTC.

## 7. Rutas configuradas

```yaml
casa_to_trabajo:     casa_actual → trabajo
depa_to_trabajo:     depa_nuevo  → trabajo
trabajo_to_casa:     trabajo     → casa_actual
trabajo_to_depa:     trabajo     → depa_nuevo
casa_to_iteso:       casa_actual → iteso
depa_to_iteso:       depa_nuevo  → iteso
iteso_to_casa:       iteso       → casa_actual
iteso_to_depa:       iteso       → depa_nuevo
```

## 8. Dashboard

Una sola página HTML servida en `http://localhost:5000`. Plotly para todos los gráficos (interactividad sin código adicional).

### 8.1 Panel de decisión (lo principal)

Dos sub-paneles, uno por destino (Trabajo, ITESO). Cada uno muestra:

- Eje X: hora del día (0-23)
- Eje Y: minutos de viaje (mediana)
- Dos líneas: `casa actual → destino` (azul) y `depa nuevo → destino` (naranja)
- Banda sombreada p25-p75 alrededor de cada línea para ver variabilidad
- Anotación dinámica del delta máximo (la franja horaria con mayor diferencia entre orígenes)

Es **la** vista que responde *¿me mudo o no?* en segundos.

### 8.2 Heatmaps por ruta

8 mini-heatmaps en grid:

- Eje X: día de semana (L–D)
- Eje Y: hora del día (6–23)
- Color: minutos de viaje mediano
- Permite detectar patrones tipo "lunes 8am es 2× más lento que miércoles 8am".

### 8.3 Distribuciones

Boxplot horizontal, una caja por ruta. Mediana, p25-p75, p10-p90, outliers. Permite comparar variabilidad entre rutas.

### 8.4 Timeline

Línea de tiempo: mediana diaria por ruta a lo largo de las semanas. Útil para detectar:

- Días con datos anómalos (festivos, cierres de calles)
- Tendencias temporales
- Cobertura de muestreo (huecos de datos)

### 8.5 Filtros + tabla

Controles arriba:
- Selector multi de rutas
- Rango de fechas
- Selector multi de días de semana

Tabla debajo: stats agregadas (N, media, mediana, p90, min, max, σ).

Todos los paneles arriba se filtran con estos controles.

## 9. Stack

| Capa | Librería | Por qué |
|---|---|---|
| Lenguaje | Python 3.11+ | Standard, fácil ad-hoc analysis |
| HTTP | `requests` | Sencillo, suficiente |
| Config | `PyYAML` | Legible para no-código |
| DB | `sqlite3` (stdlib) | Cero deps, archivo único, queryable |
| Datos | `pandas` | Agregaciones por hora/día |
| Charts | `plotly` | Interactividad sin JS custom |
| Web | `flask` | Mínimo viable, ~30 líneas |
| Scheduler | `launchd` (macOS) | Nativo, sobrevive reinicios |

## 10. Estructura de archivos

```
time-travel-tracker/
├── README.md
├── requirements.txt
├── .gitignore
├── config.example.yaml
├── config.yaml                   # gitignored
├── data/
│   ├── samples.db                # gitignored
│   └── sample.log                # gitignored
├── tracker/
│   ├── __init__.py
│   ├── db.py                     # schema + connect + insert
│   ├── routes_api.py             # cliente Routes
│   ├── sample.py                 # CLI: muestrear una vez
│   ├── analyze.py                # CLI: resumen texto (ya existe)
│   ├── dashboard.py              # Flask app
│   └── queries.py                # SQL/pandas reutilizable entre analyze y dashboard
├── scripts/
│   ├── run_sample.sh             # entrypoint launchd
│   ├── run_dashboard.sh          # arranca Flask
│   └── com.crdo.time-travel-tracker.plist   # template, se instala a ~/Library/LaunchAgents/
└── docs/
    └── superpowers/specs/
        └── 2026-05-11-time-travel-tracker-design.md
```

## 11. Costo estimado

- 8,400 calls/mes × $10/1k = **$84 USD/mes**
- Crédito gratis Google Maps Platform: $200/mes
- Net mensual: **$0** durante el experimento

Para tranquilidad, el sampler incluye un guard opcional: si las llamadas exitosas del mes en curso (contadas en SQLite) exceden un umbral configurable (default 15,000), aborta antes de llamar la API. Default desactivado en config.

## 12. Plan de uso

1. Setup inicial (config + API key + venv + DB init): 5 minutos.
2. Cargar `.plist` con `launchctl load`: 1 minuto.
3. Dejar correr 2-3 semanas.
4. Abrir dashboard cuando se quiera mirar.
5. Decidir.
6. `launchctl unload` para detener.

## 13. Open questions (no bloquean implementación)

- ¿Vale la pena agregar push de Slack/email cuando se detecten anomalías? — fuera de scope v1.
- ¿Considerar BICI/WALK como modos alternativos para tramos cortos? — fuera de scope v1.
- ¿Anotar manualmente festivos/eventos en una tabla aparte para filtrarlos? — fuera de scope v1, se puede hacer ad-hoc con SQL.
