"""ASGI config for Aegis-Credit."""

from __future__ import annotations

import os

from django.core.asgi import get_asgi_application


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aegis_credit.settings")

application = get_asgi_application()
