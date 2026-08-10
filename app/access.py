from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden

from .models import SensitiveDataAccessLog


ROLE_GROUPS = {
    "analyst": {"Analysts", "Reviewers", "Administrators"},
    "reviewer": {"Reviewers", "Administrators"},
    "admin": {"Administrators"},
}


def user_role(user: Any) -> str:
    if not getattr(user, "is_authenticated", False):
        return "local" if not settings.LOGIN_REQUIRED else "anonymous"
    if user.is_superuser or user.groups.filter(name="Administrators").exists():
        return "admin"
    if user.groups.filter(name="Reviewers").exists():
        return "reviewer"
    return "analyst"


def access_required(role: str = "analyst") -> Callable:
    allowed_groups = ROLE_GROUPS[role]

    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            if not settings.LOGIN_REQUIRED:
                return view_func(request, *args, **kwargs)
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
            if request.user.is_superuser or request.user.groups.filter(name__in=allowed_groups).exists():
                return view_func(request, *args, **kwargs)
            return HttpResponseForbidden("Your account does not have access to this area.")

        return wrapped

    return decorator


def record_sensitive_access(request: HttpRequest, action: str, obj: Any) -> None:
    """Record access metadata without copying any applicant data into logs."""
    try:
        SensitiveDataAccessLog.objects.create(
            actor=request.user if request.user.is_authenticated else None,
            action=action,
            object_type=obj.__class__.__name__,
            object_id=str(obj.pk),
            ip_address=request.META.get("REMOTE_ADDR") or None,
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
        )
    except Exception:
        # An unavailable audit sink must be visible to operations, but must not
        # turn a retrieval request into an accidental denial of service.
        import logging

        logging.getLogger(__name__).exception("Unable to record sensitive-data access")
