#!/bin/bash
# Sincroniza los repos de documentación y reindexa lo que haya cambiado.
# Pensado para correr por cron. Loguea todo con timestamps.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -d ".venv" ]; then
  source .venv/bin/activate
fi

echo "===== $(date '+%Y-%m-%d %H:%M:%S') - Iniciando actualización ====="

python3 scripts/sync_docs.py
python3 scripts/index.py

echo "===== $(date '+%Y-%m-%d %H:%M:%S') - Actualización completa ====="
