from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from app.models import AssessmentCase, CaseOutcome, CaseReviewEvent


REQUIRED_COLUMNS = {
    "case_id",
    "outcome",
    "outcome_date",
    "performance_window_end",
    "as_of_date",
    "source",
}


class Command(BaseCommand):
    help = "Validate and import mature case outcomes from a controlled CSV feed."

    def add_arguments(self, parser):
        parser.add_argument("csv_path")
        parser.add_argument("--actor", required=True, help="Existing staff username.")
        parser.add_argument("--confirm", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        path = Path(options["csv_path"]).resolve()
        if not path.is_file():
            raise CommandError(f"Outcome file not found: {path}")
        try:
            actor = get_user_model().objects.get(username=options["actor"], is_active=True)
        except get_user_model().DoesNotExist as exc:
            raise CommandError("--actor must identify an active staff account.") from exc

        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
            if missing:
                raise CommandError(f"Missing columns: {', '.join(sorted(missing))}")
            rows = list(reader)
        if not rows:
            raise CommandError("Outcome file contains no data rows.")

        prepared: list[tuple[AssessmentCase, CaseOutcome]] = []
        errors: list[str] = []
        seen_cases: set[str] = set()
        for row_number, row in enumerate(rows, start=2):
            case_id = str(row.get("case_id", "")).strip()
            if case_id in seen_cases:
                errors.append(f"row {row_number}: duplicate case_id in import")
                continue
            seen_cases.add(case_id)
            try:
                case = AssessmentCase.objects.get(id=case_id)
            except (AssessmentCase.DoesNotExist, ValueError):
                errors.append(f"row {row_number}: unknown case_id")
                continue
            if CaseOutcome.objects.filter(case=case).exists():
                errors.append(f"row {row_number}: outcome already recorded")
                continue
            try:
                outcome = CaseOutcome(
                    case=case,
                    recorded_by=actor,
                    outcome=str(row["outcome"]).strip(),
                    outcome_date=date.fromisoformat(str(row["outcome_date"]).strip()),
                    performance_window_end=date.fromisoformat(
                        str(row["performance_window_end"]).strip()
                    ),
                    as_of_date=date.fromisoformat(str(row["as_of_date"]).strip()),
                    exposure_at_default=self._decimal(row.get("exposure_at_default")),
                    loss_amount=self._decimal(row.get("loss_amount")),
                    source=str(row["source"]).strip(),
                    source_reference=str(row.get("source_reference", "")).strip(),
                    notes=str(row.get("notes", "")).strip(),
                )
                outcome.full_clean()
                if (
                    outcome.outcome == CaseOutcome.Outcome.PERFORMING
                    and outcome.performance_window_end > outcome.as_of_date
                ):
                    raise ValidationError("performing label has not reached maturity")
                if outcome.loss_amount is not None and outcome.exposure_at_default is not None:
                    if outcome.loss_amount > outcome.exposure_at_default:
                        raise ValidationError("loss exceeds exposure")
            except (ValidationError, InvalidOperation, ValueError) as exc:
                errors.append(f"row {row_number}: {exc}")
                continue
            prepared.append((case, outcome))

        self.stdout.write(f"Validated {len(prepared)} of {len(rows)} outcome rows.")
        if errors:
            raise CommandError("Outcome import rejected atomically:\n" + "\n".join(errors[:50]))
        if not options["confirm"]:
            self.stdout.write("Dry run only. Add --confirm to create immutable outcomes.")
            transaction.set_rollback(True)
            return

        for case, outcome in prepared:
            outcome.save()
            before = {"review_version": case.review_version}
            case.review_version += 1
            case.save(update_fields=["review_version", "updated_at"])
            CaseReviewEvent.objects.create(
                case=case,
                actor=actor,
                event_type=CaseReviewEvent.EventType.OUTCOME,
                review_version=case.review_version,
                before_state=before,
                after_state={"review_version": case.review_version, "outcome": outcome.outcome},
                reason="Outcome imported from controlled CSV feed.",
            )
        self.stdout.write(self.style.SUCCESS(f"Imported {len(prepared)} mature outcomes."))

    @staticmethod
    def _decimal(value):
        normalized = str(value or "").strip()
        return Decimal(normalized) if normalized else None
