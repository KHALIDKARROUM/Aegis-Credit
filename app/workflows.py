"""Transactional application workflows shared by HTTP and background workers."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import services
from .models import AssessmentCase, BatchAssessment, PredictionAudit


class IdempotencyConflict(RuntimeError):
    """The same scoped idempotency key was used for different normalized input."""


def deployment_stage() -> str:
    if settings.LOCAL_DEMO_MODE:
        return AssessmentCase.DeploymentStage.LOCAL_DEMO
    return AssessmentCase.DeploymentStage.APPROVED


def model_release_id(bundle: dict[str, Any]) -> str:
    return str(
        bundle.get("release_id")
        or bundle.get("artifact_sha256")
        or bundle.get("model_sha256")
        or bundle.get("git_commit")
        or ""
    )[:96]


@transaction.atomic
def persist_assessment(
    *,
    actor: Any,
    result: dict[str, Any],
    bundle: dict[str, Any],
    warnings: list[str],
    source: str,
    namespace: str,
    batch: BatchAssessment | None = None,
) -> tuple[AssessmentCase, bool]:
    request_id = result["request_id"]
    if not isinstance(request_id, uuid.UUID):
        request_id = uuid.UUID(str(request_id))
    accepted_digests = services.request_digests(result)
    digest = accepted_digests[0]
    stage = deployment_stage()
    reference = str(result.get("applicant_reference", "")).strip()
    due_at = timezone.now() + timedelta(hours=settings.CASE_REVIEW_SLA_HOURS)

    case, created = AssessmentCase.objects.select_for_update().get_or_create(
        idempotency_namespace=namespace,
        request_id=request_id,
        defaults={
            "request_digest": digest,
            "created_by": actor,
            "batch": batch,
            "source": source,
            "applicant_reference": reference,
            "applicant_reference_digest": services.reference_digest(reference) if reference else "",
            "application_data": services.json_safe_application(result),
            "probability": result["probability"],
            "threshold": result["threshold"],
            "risk_category": result["category"],
            "screening_result": result["prediction"],
            "recommendation": result["decision"],
            "model_version": str(bundle.get("model_version", "legacy")),
            "model_release_id": model_release_id(bundle),
            "deployment_stage": stage,
            "explanation_rows": result["explanation_rows"],
            "explanation_method": result["explanation_method"],
            "warnings": warnings,
            "due_at": due_at,
        },
    )
    if not created and case.request_digest not in accepted_digests:
        raise IdempotencyConflict(
            "The idempotency key was already used with different application data."
        )

    PredictionAudit.objects.get_or_create(
        idempotency_namespace=namespace,
        request_id=request_id,
        defaults={
            "case": case,
            "actor": actor,
            "source": source,
            "request_digest": digest,
            "feature_digest": services.feature_digest(result["application"]),
            "digest_version": "hmac-sha256-v1",
            "probability": case.probability,
            "threshold": case.threshold,
            "risk_category": case.risk_category,
            "decision": case.recommendation,
            "model_version": case.model_version,
            "deployment_stage": stage,
        },
    )
    return case, created
