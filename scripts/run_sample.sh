#!/bin/bash
# Entrypoint for launchd. Activates venv, runs one sampling pass.
set -e
cd "$(dirname "$0")/.."
mkdir -p data
source .venv/bin/activate
PYTHONPATH=. python -m tracker.sample config.yaml >> data/sample.log 2>&1
