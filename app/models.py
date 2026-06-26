from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class PredictionAudit(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    request_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    feature_digest = models.CharField(max_length=64)
    digest_version = models.CharField(max_length=24, default="hmac-sha256-v1")
    probability = models.FloatField()
    threshold = models.FloatField()
    risk_category = models.CharField(max_length=16)
    decision = models.CharField(max_length=80)
    model_version = models.CharField(max_length=32)
    source = models.CharField(max_length=16, default="web")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="prediction_audits",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.model_version}: {self.risk_category} ({self.probability:.3f})"


class AssessmentCase(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        IN_REVIEW = "in_review", "In review"
        REFERRED = "referred", "Referred"
        CLEARED = "cleared", "Cleared"
        CLOSED = "closed", "Closed"

    class OverrideDecision(models.TextChoices):
        NONE = "", "No override"
        STANDARD = "standard_review", "Continue with standard review"
        MANUAL = "manual_review", "Refer for manual review"
        ENHANCED = "enhanced_review", "Refer for enhanced review"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="created_assessment_cases",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="assigned_assessment_cases",
    )
    source = models.CharField(max_length=16, default="web")
    applicant_reference = models.CharField(max_length=80, blank=True, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
        db_index=True,
    )
    application_data = models.JSONField(default=dict)
    probability = models.FloatField()
    threshold = models.FloatField()
    risk_category = models.CharField(max_length=16)
    screening_result = models.CharField(max_length=120)
    recommendation = models.CharField(max_length=120)
    model_version = models.CharField(max_length=32)
    explanation_rows = models.JSONField(default=list)
    explanation_method = models.CharField(max_length=255, blank=True)
    warnings = models.JSONField(default=list)
    reviewer_notes = models.TextField(blank=True)
    override_decision = models.CharField(
        max_length=32,
        choices=OverrideDecision.choices,
        blank=True,
    )
    override_reason = models.TextField(blank=True)
    legal_hold = models.BooleanField(default=False)
    reviewed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["risk_category", "-created_at"]),
        ]

    def __str__(self) -> str:
        reference = self.applicant_reference or str(self.id)[:8]
        return f"{reference}: {self.risk_category} ({self.probability:.3f})"

    @property
    def effective_recommendation(self) -> str:
        return self.get_override_decision_display() if self.override_decision else self.recommendation

    @property
    def probability_percent(self) -> str:
        return f"{self.probability:.1%}"


class BatchAssessment(models.Model):
    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"
        COMPLETE = "complete", "Complete"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="batch_assessments",
    )
    file_name = models.CharField(max_length=255)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PROCESSING,
    )
    total_rows = models.PositiveIntegerField(default=0)
    valid_rows = models.PositiveIntegerField(default=0)
    invalid_rows = models.PositiveIntegerField(default=0)
    results = models.JSONField(default=list)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.file_name}: {self.get_status_display()}"
