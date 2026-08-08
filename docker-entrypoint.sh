#!/bin/sh
set -e

# Migrate database and collect static files, then exec the container CMD
echo "[entrypoint] Waiting for DB..."
# Optionally you could add a wait-for script here

echo "[entrypoint] Running migrations"
python manage.py migrate --noinput || true

echo "[entrypoint] Collecting static files"
python manage.py collectstatic --noinput || true

echo "[entrypoint] Starting application"
exec "$@"
