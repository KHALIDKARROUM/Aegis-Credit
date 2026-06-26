from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from app.models import AssessmentCase, BatchAssessment, PredictionAudit


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

    def handle(self, *args, **options):
        days = options["days"]
        cutoff = timezone.now() - timedelta(days=days)
        held_request_ids = AssessmentCase.objects.filter(legal_hold=True).values(
            "request_id"
        )
        querysets = {
            "cases": AssessmentCase.objects.filter(
                created_at__lt=cutoff,
                legal_hold=False,
            ),
            "batches": BatchAssessment.objects.filter(created_at__lt=cutoff),
            "audits": PredictionAudit.objects.filter(created_at__lt=cutoff).exclude(
                request_id__in=held_request_ids
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
        for queryset in querysets.values():
            queryset.delete()
        self.stdout.write(self.style.SUCCESS("Retention purge completed."))
