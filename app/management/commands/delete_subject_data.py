from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from app.models import AssessmentCase, BatchAssessment, PredictionAudit


class Command(BaseCommand):
    help = "Permanently delete retained data for an applicant reference (data-subject request)."

    def add_arguments(self, parser):
        parser.add_argument("--applicant-reference", required=True)
        parser.add_argument("--confirm", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        reference = options["applicant_reference"].strip()
        if not reference:
            raise CommandError("--applicant-reference must not be blank.")
        cases = AssessmentCase.objects.filter(applicant_reference=reference)
        case_request_ids = list(cases.values_list("request_id", flat=True))
        batches = []
        for batch in BatchAssessment.objects.all().iterator():
            if any(str(row.get("applicant_reference", "")) == reference for row in batch.results):
                batches.append(batch)
        counts = {
            "cases": cases.count(),
            "audits": PredictionAudit.objects.filter(request_id__in=case_request_ids).count(),
            "batches": len(batches),
        }
        self.stdout.write(", ".join(f"{name}={count}" for name, count in counts.items()))
        if not options["confirm"]:
            self.stdout.write("Dry run only. Verify the request and add --confirm to erase data.")
            return
        PredictionAudit.objects.filter(request_id__in=case_request_ids).delete()
        cases.delete()
        for batch in batches:
            batch.delete()
        self.stdout.write(self.style.SUCCESS("Data-subject deletion completed."))
