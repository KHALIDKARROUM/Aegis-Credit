"""URL configuration for BankRisk Compass."""

from __future__ import annotations

from django.urls import include, path


urlpatterns = [
    path("", include("app.urls")),
]
