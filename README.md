# time-travel-tracker

Sondea Google Routes API cada 20 min (06:00–23:00 hora local) y guarda duraciones reales con tráfico para comparar commutes a lo largo del tiempo.

Caso de uso: ¿me conviene mudarme? Compara `casa actual → trabajo` vs `depa nuevo → trabajo` con datos reales recolectados 2-4 semanas.

## Setup

```bash
cd /Users/crdo/Documents/mierdas/tools/time-travel-tracker

# venv + deps
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# config: pega tu API key
cp config.example.yaml config.yaml
$EDITOR config.yaml

# prueba manual (1 pasada de muestreo)
PYTHONPATH=. python -m tracker.sample config.yaml
```

Si imprime 8 tiempos por ruta, está funcionando.

## Tests

```bash
source .venv/bin/activate
PYTHONPATH=. pytest tests/ -v
```

22 tests, deben pasar todos.

## Dashboard

```bash
./scripts/run_dashboard.sh
# luego abre http://127.0.0.1:5000
```

Muestra: panel de decisión (casa vs depa), heatmaps por ruta, distribuciones, evolución diaria y tabla de stats.

## Schedule con launchd (macOS)

```bash
# instalar
cp scripts/com.crdo.time-travel-tracker.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.crdo.time-travel-tracker.plist

# verificar
launchctl list | grep time-travel-tracker

# detener
launchctl unload ~/Library/LaunchAgents/com.crdo.time-travel-tracker.plist
```

Logs en `data/launchd.out.log`, `data/launchd.err.log` y `data/sample.log`.

## Costo

Google Maps Platform: $200 USD/mes de crédito gratis.
Este setup (20 min, 8 rutas): 52 pasadas × 8 × 30 = ~12,480 calls/mes × $10/1k = **~$125 USD/mes → cubierto**.

Para activar un guard duro, en `config.yaml`:
```yaml
max_monthly_calls: 15000
```
Si el conteo de muestras exitosas del mes en curso (UTC) excede ese número, la siguiente pasada aborta sin pegarle a la API.
# TimeTravelCompare
