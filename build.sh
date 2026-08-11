#!/usr/bin/env bash
set -o errexit

python -m pip install --disable-pip-version-check -r requirements-prod.txt
python manage.py collectstatic --no-input
python manage.py check --deploy
