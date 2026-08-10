from django.contrib import admin

from .models import AssessmentCase, BatchAssessment, PredictionAudit, SensitiveDataAccessLog


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
    readonly_fields = ("id", "request_id", "created_at", "updated_at")

    @admin.display(description="Case")
    def short_id(self, obj: AssessmentCase) -> str:
        return str(obj.id)[:8]


@admin.register(BatchAssessment)
class BatchAssessmentAdmin(admin.ModelAdmin):
    list_display = ("file_name", "status", "total_rows", "valid_rows", "invalid_rows", "created_at")
    list_filter = ("status",)


@admin.register(PredictionAudit)
class PredictionAuditAdmin(admin.ModelAdmin):
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
class SensitiveDataAccessLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "object_type", "object_id", "ip_address")
    list_filter = ("action", "object_type")
    search_fields = ("object_id", "actor__username")
    readonly_fields = ("created_at", "actor", "action", "object_type", "object_id", "ip_address", "user_agent")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
