#!/bin/bash
set -e

echo "[DOPA] Starting clinical platform container..."

# Apply database schema migrations
echo "[DOPA] Applying database migrations..."
python manage.py migrate --noinput

echo "[DOPA] Executing command: $@"
exec "$@"
