from __future__ import annotations

from django.http import HttpRequest, HttpResponse


SENSITIVE_PREFIXES = (
    "/cases/",
    "/batch/",
    "/monitoring/",
    "/business-policy/",
    "/reports/",
    "/report-artifacts/",
    "/api/v1/",
)


class ResponseProtectionMiddleware:
    """Prevent retained applicant/decision data from being cached by intermediaries."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        if request.path in {"/", "/assessment/"} or request.path.startswith(SENSITIVE_PREFIXES):
            response["Cache-Control"] = "private, no-store, max-age=0"
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"
        response.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; "
            "form-action 'self'; img-src 'self' data:; script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; object-src 'none'",
        )
        response.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        )
        return response
