#!/usr/bin/env bash
# Exit on error
set -o errexit

echo "[Render Build] Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "[Render Build] Compiling static assets via WhiteNoise..."
python manage.py collectstatic --noinput

echo "[Render Build] Applying PostgreSQL database migrations..."
python manage.py migrate --noinput

echo "[Render Build] Build completed successfully."
