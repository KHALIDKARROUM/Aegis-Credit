from __future__ import annotations

import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .fields import EncryptedBinaryField, EncryptedJSONField, EncryptedTextField


def batch_upload_path(instance: "BatchAssessment", filename: str) -> str:
    """Keep untrusted upload names out of storage paths."""
    return f"batch_uploads/{instance.id}/{Path(filename).name}"


class ImmutableEventModel(models.Model):
    """Application-level guard against editing an audit event after creation."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk and not self._state.adding:
            raise ValidationError(f"{self.__class__.__name__} records are immutable.")
        return super().save(*args, **kwargs)


class PredictionAudit(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    request_id = models.UUIDField(default=uuid.uuid4, db_index=True, editable=False)
    idempotency_namespace = models.CharField(max_length=96, default="legacy")
    request_digest = models.CharField(max_length=64, blank=True)
    feature_digest = models.CharField(max_length=64)
    digest_version = models.CharField(max_length=24, default="hmac-sha256-v1")
    probability = models.FloatField()
    threshold = models.FloatField()
    risk_category = models.CharField(max_length=16)
    decision = models.CharField(max_length=80)
    model_version = models.CharField(max_length=32)
    source = models.CharField(max_length=16, default="web")
    deployment_stage = models.CharField(max_length=24, default="unclassified")
    case = models.OneToOneField(
        "AssessmentCase",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="prediction_audit",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="prediction_audits",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["model_version", "-created_at"]),
            models.Index(fields=["source", "-created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["idempotency_namespace", "request_id"],
                name="uniq_audit_namespace_request",
            )
        ]

    def __str__(self) -> str:
        return f"{self.model_version}: {self.risk_category} ({self.probability:.3f})"

    def save(self, *args, **kwargs):
        if self.pk and not self._state.adding:
            raise ValidationError("Prediction audit records are append-only.")
        return super().save(*args, **kwargs)


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

    class DeploymentStage(models.TextChoices):
        LOCAL_DEMO = "local_demo", "Local demonstration"
        APPROVED = "approved", "Approved release"
        UNCLASSIFIED = "unclassified", "Unclassified"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request_id = models.UUIDField(default=uuid.uuid4, db_index=True, editable=False)
    idempotency_namespace = models.CharField(max_length=96, default="legacy")
    request_digest = models.CharField(max_length=64, blank=True)
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
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_assessment_cases",
    )
    batch = models.ForeignKey(
        "BatchAssessment",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="cases",
    )
    source = models.CharField(max_length=16, default="web")
    applicant_reference = EncryptedTextField(blank=True)
    applicant_reference_digest = models.CharField(max_length=64, blank=True, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
        db_index=True,
    )
    application_data = EncryptedJSONField(default=dict)
    probability = models.FloatField()
    threshold = models.FloatField()
    risk_category = models.CharField(max_length=16)
    screening_result = models.CharField(max_length=120)
    recommendation = models.CharField(max_length=120)
    model_version = models.CharField(max_length=32)
    model_release_id = models.CharField(max_length=96, blank=True)
    deployment_stage = models.CharField(
        max_length=24,
        choices=DeploymentStage.choices,
        default=DeploymentStage.UNCLASSIFIED,
        db_index=True,
    )
    explanation_rows = EncryptedJSONField(default=list)
    explanation_method = models.CharField(max_length=255, blank=True)
    warnings = EncryptedJSONField(default=list)
    reviewer_notes = EncryptedTextField(blank=True)
    override_decision = models.CharField(
        max_length=32,
        choices=OverrideDecision.choices,
        blank=True,
    )
    override_reason = EncryptedTextField(blank=True)
    legal_hold = models.BooleanField(default=False)
    reviewed_at = models.DateTimeField(blank=True, null=True)
    due_at = models.DateTimeField(blank=True, null=True, db_index=True)
    review_version = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["risk_category", "-created_at"]),
            models.Index(fields=["assigned_to", "status", "due_at"]),
            models.Index(fields=["model_version", "-created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["idempotency_namespace", "request_id"],
                name="uniq_case_namespace_request",
            )
        ]

    def __str__(self) -> str:
        reference = self.applicant_reference or str(self.id)[:8]
        return f"{reference}: {self.risk_category} ({self.probability:.3f})"

    @property
    def effective_recommendation(self) -> str:
        return (
            self.get_override_decision_display()
            if self.override_decision
            else "No human decision recorded"
        )

    @property
    def has_human_decision(self) -> bool:
        return bool(self.override_decision)

    @property
    def probability_percent(self) -> str:
        return f"{self.probability:.1%}"


class BatchAssessment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETE = "complete", "Complete"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

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
    input_file = models.FileField(upload_to=batch_upload_path, blank=True)
    upload_payload = EncryptedBinaryField(blank=True, default=bytes)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    total_rows = models.PositiveIntegerField(default=0)
    valid_rows = models.PositiveIntegerField(default=0)
    invalid_rows = models.PositiveIntegerField(default=0)
    results = EncryptedJSONField(default=list)
    error_message = EncryptedTextField(blank=True)
    attempts = models.PositiveIntegerField(default=0)
    cancel_requested = models.BooleanField(default=False)
    started_at = models.DateTimeField(blank=True, null=True)
    heartbeat_at = models.DateTimeField(blank=True, null=True, db_index=True)
    worker_token = models.UUIDField(blank=True, null=True, editable=False)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self) -> str:
        return f"{self.file_name}: {self.get_status_display()}"


class SensitiveDataAccessLog(models.Model):
    """Append-only audit metadata for accesses to retained applicant records."""

    created_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="sensitive_data_accesses",
    )
    action = models.CharField(max_length=64)
    object_type = models.CharField(max_length=32)
    object_id = models.CharField(max_length=64)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["object_type", "object_id", "-created_at"],
                name="app_sensiti_object__941965_idx",
            )
        ]

    def __str__(self) -> str:
        return f"{self.action} {self.object_type}/{self.object_id}"

    def save(self, *args, **kwargs):
        if self.pk and not self._state.adding:
            raise ValidationError("Sensitive access logs are append-only.")
        return super().save(*args, **kwargs)


class BatchRow(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SCORED = "scored", "Scored"
        INVALID = "invalid", "Invalid"
        FAILED = "failed", "Failed"
        REDACTED = "redacted", "Redacted"

    batch = models.ForeignKey(BatchAssessment, on_delete=models.CASCADE, related_name="rows")
    row_number = models.PositiveIntegerField()
    applicant_reference = EncryptedTextField(blank=True)
    reference_digest = models.CharField(max_length=64, blank=True, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    case = models.OneToOneField(
        AssessmentCase,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="batch_row",
    )
    result = EncryptedJSONField(default=dict)
    warnings = EncryptedJSONField(default=list)
    errors = EncryptedJSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["row_number"]
        constraints = [
            models.UniqueConstraint(fields=["batch", "row_number"], name="uniq_batch_row_number")
        ]


class CaseReviewEvent(ImmutableEventModel):
    class EventType(models.TextChoices):
        REVIEW = "review", "Review"
        ASSIGNMENT = "assignment", "Assignment"
        OUTCOME = "outcome", "Outcome recorded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(AssessmentCase, on_delete=models.CASCADE, related_name="review_events")
    created_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="case_review_events",
    )
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    review_version = models.PositiveIntegerField()
    before_state = EncryptedJSONField(default=dict)
    after_state = EncryptedJSONField(default=dict)
    reason = EncryptedTextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["case", "review_version"], name="uniq_case_review_version"
            )
        ]


class LegalHoldEvent(ImmutableEventModel):
    class Action(models.TextChoices):
        PLACED = "placed", "Placed"
        RELEASED = "released", "Released"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(AssessmentCase, on_delete=models.CASCADE, related_name="legal_hold_events")
    created_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="legal_hold_events",
    )
    action = models.CharField(max_length=12, choices=Action.choices)
    reason = EncryptedTextField()
    ticket_reference = models.CharField(max_length=120)

    class Meta:
        ordering = ["-created_at"]


class CaseOutcome(ImmutableEventModel):
    class Outcome(models.TextChoices):
        PERFORMING = "performing", "Performing"
        DEFAULTED = "defaulted", "Defaulted"
        CHARGED_OFF = "charged_off", "Charged off"
        CLOSED_OTHER = "closed_other", "Closed - other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.OneToOneField(AssessmentCase, on_delete=models.CASCADE, related_name="outcome")
    recorded_at = models.DateTimeField(auto_now_add=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="recorded_case_outcomes",
    )
    outcome = models.CharField(max_length=20, choices=Outcome.choices)
    outcome_date = models.DateField()
    performance_window_end = models.DateField()
    as_of_date = models.DateField()
    exposure_at_default = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    loss_amount = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    source = models.CharField(max_length=80)
    source_reference = models.CharField(max_length=120, blank=True)
    notes = EncryptedTextField(blank=True)

    class Meta:
        ordering = ["-recorded_at"]
        indexes = [models.Index(fields=["outcome", "outcome_date"])]


class DataDeletionReceipt(ImmutableEventModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    reference_digest = models.CharField(max_length=64, db_index=True)
    requested_by = models.CharField(max_length=120)
    deleted_cases = models.PositiveIntegerField(default=0)
    deleted_audits = models.PositiveIntegerField(default=0)
    redacted_batch_rows = models.PositiveIntegerField(default=0)
    notes = EncryptedTextField(blank=True)


class MonitoringRun(ImmutableEventModel):
    class Status(models.TextChoices):
        PASS = "pass", "Pass"
        ALERT = "alert", "Alert"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    as_of_date = models.DateField()
    window_start = models.DateField()
    window_end = models.DateField()
    model_version = models.CharField(max_length=32)
    model_release_id = models.CharField(max_length=96, blank=True)
    sample_size = models.PositiveIntegerField()
    mature_outcome_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, choices=Status.choices)
    metrics = EncryptedJSONField(default=dict)
    alerts = EncryptedJSONField(default=list)
    input_digest = models.CharField(max_length=64)
    owner = models.CharField(max_length=120)
    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["model_version", "-created_at"])]


class MonitoringAcknowledgement(ImmutableEventModel):
    class Action(models.TextChoices):
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        ESCALATED = "escalated", "Escalated"
        RESOLVED = "resolved", "Resolved"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(
        MonitoringRun, on_delete=models.CASCADE, related_name="acknowledgements"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="monitoring_acknowledgements",
    )
    action = models.CharField(max_length=16, choices=Action.choices)
    note = EncryptedTextField()

    class Meta:
        ordering = ["-created_at"]


class PolicyScenario(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="policy_scenarios",
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    assumptions = EncryptedJSONField(default=dict)
    results = EncryptedJSONField(default=dict)
    model_version = models.CharField(max_length=32)
    approved_at = models.DateTimeField(blank=True, null=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="approved_policy_scenarios",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["name", "version"], name="uniq_policy_name_version")
        ]


class PolicyScenarioEvent(ImmutableEventModel):
    class Action(models.TextChoices):
        CREATED = "created", "Created"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scenario = models.ForeignKey(PolicyScenario, on_delete=models.CASCADE, related_name="events")
    created_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="policy_scenario_events",
    )
    action = models.CharField(max_length=12, choices=Action.choices)
    reason = EncryptedTextField()

    class Meta:
        ordering = ["-created_at"]


class ApiRateLimitBucket(models.Model):
    key_digest = models.CharField(max_length=64)
    window_start = models.DateTimeField()
    request_count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["key_digest", "window_start"], name="uniq_api_rate_window")
        ]
