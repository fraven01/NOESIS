#!/bin/sh
set -euo pipefail

wait_for_db() {
  # bis zu 30x versuchen, DB-Verbindung aufzubauen
  ATTEMPTS=${DB_WAIT_ATTEMPTS:-30}
  SLEEP_SECS=${DB_WAIT_SLEEP:-2}
  echo "Warte auf Datenbank ($ATTEMPTS Versuche à ${SLEEP_SECS}s)..."
  i=1
  while [ $i -le $ATTEMPTS ]; do
    if python - <<'PYCODE'
import sys, os
os.environ.setdefault("DJANGO_SETTINGS_MODULE","noesis.settings")
import django
django.setup()
from django.db import connections
try:
    connections['default'].cursor()
except Exception as e:
    print(e)
    sys.exit(1)
else:
    sys.exit(0)
PYCODE
    then
      echo "DB ist erreichbar."
      return 0
    fi
    echo "DB noch nicht erreichbar (Versuch $i/$ATTEMPTS)..."
    i=$((i+1))
    sleep "$SLEEP_SECS"
  done
  echo "DB nicht erreichbar – Abbruch."
  exit 1
}

run_migrations() {
  echo "Führe Django-Migrationen aus..."
  python manage.py migrate --no-input
}

maybe_create_superuser() {
  if [ "${CREATE_SUPERUSER_ON_START:-0}" = "1" ]; then
    echo "Lege Superuser (non-interactive) an (falls nicht vorhanden)..."
    python - <<'PYCODE'
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE","noesis.settings")
django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()
u = os.environ.get("DJANGO_SUPERUSER_USERNAME","admin")
e = os.environ.get("DJANGO_SUPERUSER_EMAIL","admin@example.com")
p = os.environ.get("DJANGO_SUPERUSER_PASSWORD","admin123")
if not User.objects.filter(username=u).exists():
    User.objects.create_superuser(username=u, email=e, password=p)
    print(f"Superuser '{u}' erstellt.")
else:
    print(f"Superuser '{u}' existiert bereits.")
PYCODE
  fi
}

build_static() {
  echo "Baue CSS mit Tailwind..."
  npm --prefix theme/static_src run build
}

if [ "${1:-}" = "migrate" ]; then
  wait_for_db
  run_migrations
  exit 0
elif [ "${1:-}" = "seed" ]; then
  echo "Initialdaten werden geladen..."
  python manage.py seed_initial_data
  exit 0
elif [ "${1:-}" = "web" ]; then
  # Optional: DB-Warte- und Migrationsschritt vor dem Start
  if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    wait_for_db
    run_migrations
    maybe_create_superuser
  fi
  build_static
  echo "Starte Gunicorn..."
  exec gunicorn noesis.wsgi:application --bind 0.0.0.0:${PORT:-8080} --workers ${WORKERS:-2}
else
  exec "$@"
fi
