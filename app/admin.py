from django.contrib import admin

from .models import (
    AssessmentCase,
    BatchAssessment,
    CaseOutcome,
    CaseReviewEvent,
    DataDeletionReceipt,
    LegalHoldEvent,
    MonitoringAcknowledgement,
    MonitoringRun,
    PolicyScenario,
    PolicyScenarioEvent,
    PredictionAudit,
    SensitiveDataAccessLog,
)


class ImmutableAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AssessmentCase)
class AssessmentCaseAdmin(admin.ModelAdmin):
    list_display = (
        "short_id",
        "applicant_reference",
        "risk_category",
        "status",
        "recommendation",
        "created_at",
    )
    list_filter = ("status", "risk_category", "source", "model_version")
    search_fields = ("applicant_reference", "id")
    readonly_fields = [field.name for field in AssessmentCase._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Case")
    def short_id(self, obj: AssessmentCase) -> str:
        return str(obj.id)[:8]


@admin.register(BatchAssessment)
class BatchAssessmentAdmin(admin.ModelAdmin):
    list_display = ("file_name", "status", "total_rows", "valid_rows", "invalid_rows", "created_at")
    list_filter = ("status",)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PredictionAudit)
class PredictionAuditAdmin(ImmutableAdmin):
    list_display = ("request_id", "source", "risk_category", "probability", "model_version", "created_at")
    list_filter = ("source", "risk_category", "model_version")
    readonly_fields = (
        "request_id",
        "created_at",
        "feature_digest",
        "digest_version",
        "probability",
        "threshold",
        "risk_category",
        "decision",
        "model_version",
        "source",
        "actor",
    )


@admin.register(SensitiveDataAccessLog)
class SensitiveDataAccessLogAdmin(ImmutableAdmin):
    list_display = ("created_at", "actor", "action", "object_type", "object_id", "ip_address")
    list_filter = ("action", "object_type")
    search_fields = ("object_id", "actor__username")
    readonly_fields = ("created_at", "actor", "action", "object_type", "object_id", "ip_address", "user_agent")



@admin.register(CaseReviewEvent)
class CaseReviewEventAdmin(ImmutableAdmin):
    list_display = ("case", "event_type", "review_version", "actor", "created_at")
    list_filter = ("event_type", "created_at")


@admin.register(LegalHoldEvent)
class LegalHoldEventAdmin(ImmutableAdmin):
    list_display = ("case", "action", "ticket_reference", "actor", "created_at")
    list_filter = ("action", "created_at")


@admin.register(CaseOutcome)
class CaseOutcomeAdmin(ImmutableAdmin):
    list_display = ("case", "outcome", "outcome_date", "as_of_date", "recorded_by")
    list_filter = ("outcome", "outcome_date")


@admin.register(DataDeletionReceipt)
class DataDeletionReceiptAdmin(ImmutableAdmin):
    list_display = ("created_at", "reference_digest", "deleted_cases", "deleted_audits")


@admin.register(MonitoringRun)
class MonitoringRunAdmin(ImmutableAdmin):
    list_display = ("created_at", "model_version", "window_start", "window_end", "status")
    list_filter = ("status", "model_version")


@admin.register(MonitoringAcknowledgement)
class MonitoringAcknowledgementAdmin(ImmutableAdmin):
    list_display = ("run", "action", "actor", "created_at")
    list_filter = ("action", "created_at")


@admin.register(PolicyScenario)
class PolicyScenarioAdmin(ImmutableAdmin):
    list_display = ("name", "version", "model_version", "status", "created_at")
    list_filter = ("status", "model_version")


@admin.register(PolicyScenarioEvent)
class PolicyScenarioEventAdmin(ImmutableAdmin):
    list_display = ("scenario", "action", "actor", "created_at")
    list_filter = ("action", "created_at")
