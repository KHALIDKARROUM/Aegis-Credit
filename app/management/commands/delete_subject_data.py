from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from app import services
from app.models import (
    AssessmentCase,
    BatchAssessment,
    BatchRow,
    DataDeletionReceipt,
    PredictionAudit,
)


class Command(BaseCommand):
    help = "Permanently delete retained data for an applicant reference (data-subject request)."

    def add_arguments(self, parser):
        parser.add_argument("--applicant-reference", required=True)
        parser.add_argument("--requested-by", required=True)
        parser.add_argument("--confirm", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        reference = options["applicant_reference"].strip()
        if not reference:
            raise CommandError("--applicant-reference must not be blank.")
        digests = services.reference_digests(reference)
        digest = digests[0]
        cases = AssessmentCase.objects.filter(applicant_reference_digest__in=digests)
        if cases.filter(legal_hold=True).exists():
            raise CommandError(
                "Deletion is blocked because at least one matching case is under legal hold."
            )
        case_request_keys = list(
            cases.values_list("idempotency_namespace", "request_id")
        )
        # A UUID is only unique inside its idempotency namespace.  Matching on
        # request_id alone could erase another API client's otherwise unrelated
        # audit record when both clients supplied the same UUID.
        audit_scope = Q(case__in=cases)
        for namespace, request_id in case_request_keys:
            audit_scope |= Q(
                idempotency_namespace=namespace,
                request_id=request_id,
            )
        audits = PredictionAudit.objects.filter(audit_scope).distinct()
        normalized_rows = BatchRow.objects.filter(reference_digest__in=digests)
        legacy_rows = 0
        for batch in BatchAssessment.objects.all().iterator():
            legacy_rows += sum(
                str(row.get("applicant_reference", "")).strip().casefold()
                == reference.casefold()
                for row in batch.results
            )
        counts = {
            "cases": cases.count(),
            "audits": audits.count(),
            "batch_rows": normalized_rows.count() + legacy_rows,
        }
        self.stdout.write(", ".join(f"{name}={count}" for name, count in counts.items()))
        if not options["confirm"]:
            self.stdout.write("Dry run only. Verify the request and add --confirm to erase data.")
            return
        deleted_audits = audits.count()
        deleted_cases = cases.count()
        redacted_rows = normalized_rows.count()
        audits.delete()
        normalized_rows.update(
            applicant_reference="",
            reference_digest="",
            status=BatchRow.Status.REDACTED,
            case=None,
            result={},
            warnings=[],
            errors=["Applicant data removed under an authorized data-subject request."],
        )
        cases.delete()
        for batch in BatchAssessment.objects.all().iterator():
            changed = False
            output_rows = []
            for row in batch.results:
                if (
                    str(row.get("applicant_reference", "")).strip().casefold()
                    == reference.casefold()
                ):
                    output_rows.append(
                        {
                            "row": row.get("row"),
                            "applicant_reference": "",
                            "status": "redacted",
                            "warnings": [],
                            "errors": [
                                "Applicant data removed under an authorized data-subject request."
                            ],
                        }
                    )
                    changed = True
                    redacted_rows += 1
                else:
                    output_rows.append(row)
            if changed:
                batch.results = output_rows
                batch.save(update_fields=["results"])
        DataDeletionReceipt.objects.create(
            reference_digest=digest,
            requested_by=options["requested_by"].strip(),
            deleted_cases=deleted_cases,
            deleted_audits=deleted_audits,
            redacted_batch_rows=redacted_rows,
            notes="Completed through delete_subject_data management command.",
        )
        self.stdout.write(self.style.SUCCESS("Data-subject deletion completed."))
