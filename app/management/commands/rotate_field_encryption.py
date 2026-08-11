from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from app.models import (
    AssessmentCase,
    BatchAssessment,
    BatchRow,
    CaseOutcome,
    CaseReviewEvent,
    DataDeletionReceipt,
    LegalHoldEvent,
    MonitoringAcknowledgement,
    MonitoringRun,
    PolicyScenario,
    PolicyScenarioEvent,
)


ENCRYPTED_FIELDS = {
    AssessmentCase: [
        "applicant_reference",
        "application_data",
        "explanation_rows",
        "warnings",
        "reviewer_notes",
        "override_reason",
    ],
    BatchAssessment: ["results", "error_message", "upload_payload"],
    BatchRow: ["applicant_reference", "result", "warnings", "errors"],
    CaseReviewEvent: ["before_state", "after_state", "reason"],
    LegalHoldEvent: ["reason"],
    CaseOutcome: ["notes"],
    DataDeletionReceipt: ["notes"],
    MonitoringRun: ["metrics", "alerts"],
    MonitoringAcknowledgement: ["note"],
    PolicyScenario: ["assumptions", "results"],
    PolicyScenarioEvent: ["reason"],
}


class Command(BaseCommand):
    help = "Re-encrypt every protected value with the first FIELD_ENCRYPTION_KEYS key."

    def add_arguments(self, parser):
        parser.add_argument("--confirm", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        counts = {model.__name__: model.objects.count() for model in ENCRYPTED_FIELDS}
        self.stdout.write(", ".join(f"{name}={count}" for name, count in counts.items()))
        if not options["confirm"]:
            self.stdout.write(
                "Dry run only. Configure the new active key first, retain old keys for reading, "
                "then add --confirm."
            )
            return
        for model, field_names in ENCRYPTED_FIELDS.items():
            for obj in model.objects.only("pk", *field_names).iterator(chunk_size=200):
                values = {field_name: getattr(obj, field_name) for field_name in field_names}
                # QuerySet.update deliberately bypasses immutable event save guards;
                # logical content is unchanged and only ciphertext is rotated.
                model.objects.filter(pk=obj.pk).update(**values)
        self.stdout.write(self.style.SUCCESS("Protected fields were re-encrypted."))
