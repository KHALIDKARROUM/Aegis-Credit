#!/usr/bin/env sh
set -eu

python manage.py migrate --no-input
python manage.py bootstrap_roles
exec gunicorn bankrisk_compass.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${WEB_CONCURRENCY:-2}" \
  --threads "${GUNICORN_THREADS:-2}" \
  --timeout "${GUNICORN_TIMEOUT:-120}"
