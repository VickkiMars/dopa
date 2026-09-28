#!/bin/bash
set -e

echo "[DOPA] Starting clinical platform container on PORT ${PORT:-8000}..."

# Apply database schema migrations
echo "[DOPA] Applying database migrations..."
if python manage.py migrate --noinput; then
    echo "[DOPA] Database migrations applied successfully."
else
    echo "[DOPA Warning] Migrations failed or database is unreachable. Proceeding with web server startup..."
fi

echo "[DOPA] Executing command: $@"
exec "$@"
