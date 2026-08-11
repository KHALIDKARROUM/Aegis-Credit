from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from .models import AssessmentCase, BatchAssessment, SensitiveDataAccessLog


ROLE_GROUPS = {
    "analyst": {"Analysts", "Reviewers", "Administrators"},
    "case": {"Analysts", "Reviewers", "Legal Officers", "Administrators"},
    "reviewer": {"Reviewers", "Administrators"},
    "monitoring": {"Reviewers", "Legal Officers", "Administrators"},
    "legal": {"Legal Officers", "Administrators"},
    "admin": {"Administrators"},
}


def user_role(user: Any) -> str:
    if not getattr(user, "is_authenticated", False):
        return "local" if not settings.LOGIN_REQUIRED else "anonymous"
    if user.is_superuser or user.groups.filter(name="Administrators").exists():
        return "admin"
    if user.groups.filter(name="Legal Officers").exists():
        return "legal"
    if user.groups.filter(name="Reviewers").exists():
        return "reviewer"
    if user.groups.filter(name="Analysts").exists():
        return "analyst"
    return "unassigned"


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
            return render(request, "403.html", status=403)

        return wrapped

    return decorator


def record_sensitive_access(request: HttpRequest, action: str, obj: Any) -> None:
    """Record access metadata without copying any applicant data into logs."""
    SensitiveDataAccessLog.objects.create(
        actor=request.user if request.user.is_authenticated else None,
        action=action,
        object_type=obj.__class__.__name__,
        object_id=str(obj.pk),
        ip_address=request.META.get("REMOTE_ADDR") or None,
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
    )


def case_queryset_for_user(user: Any) -> QuerySet[AssessmentCase]:
    queryset = AssessmentCase.objects.all()
    role = user_role(user)
    if not settings.LOGIN_REQUIRED or role in {"reviewer", "legal", "admin", "local"}:
        return queryset
    if role == "analyst":
        return queryset.filter(Q(created_by=user) | Q(assigned_to=user)).distinct()
    return queryset.none()


def batch_queryset_for_user(user: Any) -> QuerySet[BatchAssessment]:
    queryset = BatchAssessment.objects.all()
    role = user_role(user)
    if not settings.LOGIN_REQUIRED or role in {"reviewer", "legal", "admin", "local"}:
        return queryset
    if role == "analyst":
        return queryset.filter(created_by=user)
    return queryset.none()


def can_manage_legal_holds(user: Any) -> bool:
    return user_role(user) in {"legal", "admin", "local"}
