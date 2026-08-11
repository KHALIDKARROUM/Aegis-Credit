from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from app.models import (
    ApiRateLimitBucket,
    AssessmentCase,
    BatchAssessment,
    PredictionAudit,
    SensitiveDataAccessLog,
)


class Command(BaseCommand):
    help = "Delete case, batch, and audit records older than the retention period."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=settings.CASE_RETENTION_DAYS,
            help="Retention period in days.",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Perform deletion. Without this flag the command is a dry run.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        days = options["days"]
        if days < 1:
            raise CommandError("--days must be at least 1.")
        cutoff = timezone.now() - timedelta(days=days)
        held_cases = list(
            AssessmentCase.objects.filter(legal_hold=True).values("request_id", "batch_id")
        )
        # Materialize identifiers before any delete. A lazy subquery would be
        # re-evaluated after cases are removed and could erase held audits.
        held_request_ids = [row["request_id"] for row in held_cases]
        held_batch_ids = {row["batch_id"] for row in held_cases if row["batch_id"]}
        held_case_ids = list(
            AssessmentCase.objects.filter(legal_hold=True).values_list("id", flat=True)
        )
        held_object_filter = Q(object_type="AssessmentCase", object_id__in=[str(i) for i in held_case_ids])
        if held_batch_ids:
            held_object_filter |= Q(
                object_type="BatchAssessment",
                object_id__in=[str(i) for i in held_batch_ids],
            )
        querysets = {
            "cases": AssessmentCase.objects.filter(
                created_at__lt=cutoff,
                legal_hold=False,
            ),
            "batches": BatchAssessment.objects.filter(created_at__lt=cutoff).exclude(
                id__in=held_batch_ids
            ),
            "audits": PredictionAudit.objects.filter(created_at__lt=cutoff).exclude(
                request_id__in=held_request_ids
            ),
            "access_logs": SensitiveDataAccessLog.objects.filter(
                created_at__lt=timezone.now() - timedelta(days=settings.ACCESS_LOG_RETENTION_DAYS)
            ).exclude(held_object_filter),
            "rate_buckets": ApiRateLimitBucket.objects.filter(
                window_start__lt=timezone.now() - timedelta(days=1)
            ),
        }
        counts = {name: queryset.count() for name, queryset in querysets.items()}
        self.stdout.write(
            f"Records older than {days} days: "
            + ", ".join(f"{name}={count}" for name, count in counts.items())
        )
        if not options["confirm"]:
            self.stdout.write("Dry run only. Add --confirm to delete these records.")
            return
        # Delete audits first while the materialized legal-hold exclusion is
        # still available. Related immutable events follow their non-held case.
        querysets["audits"].delete()
        querysets["access_logs"].delete()
        querysets["rate_buckets"].delete()
        querysets["cases"].delete()
        for batch in querysets["batches"].only("input_file"):
            if batch.input_file:
                batch.input_file.delete(save=False)
        querysets["batches"].delete()
        self.stdout.write(self.style.SUCCESS("Retention purge completed."))
