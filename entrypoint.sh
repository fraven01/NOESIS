#!/bin/sh
set -e

if [ "$1" = "migrate" ]; then
    echo "Datenbank-Migrationen werden ausgeführt..."
    python manage.py migrate --no-input
elif [ "$1" = "seed" ]; then
    echo "Initialdaten werden geladen..."
    python manage.py seed_initial_data
elif [ "$1" = "web" ]; then
    echo "Gunicorn-Server wird gestartet..."
    exec gunicorn --bind 0.0.0.0:$PORT noesis.wsgi:application
else
    exec "$@"
fi
