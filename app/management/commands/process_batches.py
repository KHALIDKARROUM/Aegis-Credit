from __future__ import annotations

import time

from django.core.management.base import BaseCommand

from app.batch_processing import process_batch, recover_stale_batches
from app.models import BatchAssessment


class Command(BaseCommand):
    help = "Process durable pending batch jobs."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Exit when no pending jobs remain.")
        parser.add_argument("--poll-seconds", type=float, default=2.0)
        parser.add_argument("--retry-failed", action="store_true")

    def handle(self, *args, **options):
        poll_seconds = max(0.25, min(float(options["poll_seconds"]), 60.0))
        while True:
            recovered = recover_stale_batches()
            if recovered:
                self.stderr.write(f"Recovered {recovered} stale batch lease(s).")
            statuses = [BatchAssessment.Status.PENDING]
            if options["retry_failed"]:
                statuses.append(BatchAssessment.Status.FAILED)
            batch = BatchAssessment.objects.filter(status__in=statuses).order_by("created_at").first()
            if batch is None:
                if options["once"]:
                    return
                time.sleep(poll_seconds)
                continue
            try:
                process_batch(batch.id, retry_failed=options["retry_failed"])
            except Exception as exc:
                self.stderr.write(f"Batch {batch.id} failed: {exc}")
            else:
                self.stdout.write(f"Processed batch {batch.id}")
