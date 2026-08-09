#!/usr/bin/env bash
set -e

# Simple start script for deployments: run migrations, collectstatic, then start Daphne
echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting Daphne ASGI server..."
exec daphne -b 0.0.0.0 -p 8000 cloudvault.asgi:application
