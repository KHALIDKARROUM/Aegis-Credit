"""Durable, retryable processing for uploaded assessment batches."""

from __future__ import annotations

import io
import uuid
from datetime import timedelta
from typing import Any

import pandas as pd
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from . import services
from .forms import ApplicantAssessmentForm
from .models import BatchAssessment, BatchRow
from .workflows import IdempotencyConflict, persist_assessment


def _row_payload(raw_row: Any, request_id: uuid.UUID) -> dict[str, Any]:
    payload = {
        key: ("" if pd.isna(value) else value)
        for key, value in raw_row.to_dict().items()
    }
    payload["request_id"] = request_id
    return payload


def process_batch(batch_id: uuid.UUID, *, retry_failed: bool = False) -> BatchAssessment:
    worker_token = uuid.uuid4()
    with transaction.atomic():
        batch = BatchAssessment.objects.select_for_update().get(id=batch_id)
        allowed = {BatchAssessment.Status.PENDING}
        if retry_failed:
            allowed.add(BatchAssessment.Status.FAILED)
        if batch.status not in allowed:
            return batch
        if batch.cancel_requested:
            batch.status = BatchAssessment.Status.CANCELLED
            batch.completed_at = timezone.now()
            legacy_file = batch.input_file
            batch.input_file = ""
            batch.upload_payload = b""
            batch.save(
                update_fields=["status", "completed_at", "input_file", "upload_payload"]
            )
            if legacy_file:
                legacy_file.delete(save=False)
            return batch
        batch.status = BatchAssessment.Status.PROCESSING
        batch.started_at = timezone.now()
        batch.heartbeat_at = batch.started_at
        batch.worker_token = worker_token
        batch.attempts += 1
        batch.error_message = ""
        batch.save(
            update_fields=[
                "status",
                "started_at",
                "heartbeat_at",
                "worker_token",
                "attempts",
                "error_message",
            ]
        )

    try:
        bundle = services.load_model_bundle()
        if batch.upload_payload:
            upload = io.BytesIO(batch.upload_payload)
            upload.name = batch.file_name
            frame = services.read_batch_upload(upload)
        elif batch.input_file:
            with batch.input_file.open("rb") as upload:
                frame = services.read_batch_upload(upload)
        else:
            raise ValueError("The persisted batch upload is unavailable.")
        batch.total_rows = len(frame)
        batch.save(update_fields=["total_rows"])

        for index, raw_row in frame.iterrows():
            batch.refresh_from_db(fields=["cancel_requested", "worker_token"])
            if batch.worker_token != worker_token:
                raise RuntimeError("Batch processing lease was lost.")
            if batch.cancel_requested:
                batch.status = BatchAssessment.Status.CANCELLED
                batch.completed_at = timezone.now()
                batch.worker_token = None
                batch.save(update_fields=["status", "completed_at", "worker_token"])
                return batch
            batch.heartbeat_at = timezone.now()
            batch.save(update_fields=["heartbeat_at"])

            row_number = int(index) + 2
            request_id = uuid.uuid5(batch.id, f"row:{row_number}")
            payload = _row_payload(raw_row, request_id)
            reference = str(payload.get("applicant_reference", "")).strip()
            row, _ = BatchRow.objects.get_or_create(
                batch=batch,
                row_number=row_number,
                defaults={
                    "applicant_reference": reference,
                    "reference_digest": services.reference_digest(reference) if reference else "",
                },
            )
            if row.status in {BatchRow.Status.SCORED, BatchRow.Status.INVALID}:
                continue

            form = ApplicantAssessmentForm(payload, bundle=bundle)
            if not form.is_valid():
                errors = [
                    f"{field}: {message}"
                    for field, messages_for_field in form.errors.items()
                    for message in messages_for_field
                ]
                row.status = BatchRow.Status.INVALID
                row.errors = errors
                row.warnings = []
                row.result = {}
                row.save(update_fields=["status", "errors", "warnings", "result"])
                continue

            blocks = form.distribution_blocks()
            if blocks:
                row.status = BatchRow.Status.INVALID
                row.errors = blocks
                row.warnings = form.distribution_warnings()
                row.result = {}
                row.save(update_fields=["status", "errors", "warnings", "result"])
                continue

            result = services.assessment_result(bundle, form.cleaned_data, explain=False)
            warnings = form.distribution_warnings()
            try:
                case, _ = persist_assessment(
                    actor=batch.created_by,
                    result=result,
                    bundle=bundle,
                    warnings=warnings,
                    source="batch",
                    namespace=f"batch:{batch.id}",
                    batch=batch,
                )
            except IdempotencyConflict as exc:
                row.status = BatchRow.Status.FAILED
                row.errors = [str(exc)]
                row.save(update_fields=["status", "errors"])
                continue
            row.status = BatchRow.Status.SCORED
            row.case = case
            row.warnings = warnings
            row.errors = []
            row.result = {
                "case_id": str(case.id),
                "probability": round(case.probability, 6),
                "risk_category": case.risk_category,
                "recommended_next_step": case.recommendation,
                "model_version": case.model_version,
                "deployment_stage": case.deployment_stage,
            }
            row.save(update_fields=["status", "case", "warnings", "errors", "result"])

        batch = _finalize_batch(batch, worker_token=worker_token)
    except Exception as exc:
        # A stale worker must never overwrite a batch that recovery has
        # returned to the queue or another worker has subsequently claimed.
        BatchAssessment.objects.filter(
            id=batch.id,
            status=BatchAssessment.Status.PROCESSING,
            worker_token=worker_token,
        ).update(
            status=BatchAssessment.Status.FAILED,
            error_message=str(exc),
            completed_at=timezone.now(),
            worker_token=None,
            results=_legacy_results(batch),
        )
        batch.refresh_from_db()
        raise
    finally:
        if batch.status in {
            BatchAssessment.Status.COMPLETE,
            BatchAssessment.Status.CANCELLED,
        } and batch.input_file:
            batch.input_file.delete(save=False)
            batch.input_file = ""
            batch.upload_payload = b""
            batch.save(update_fields=["input_file", "upload_payload"])
        elif batch.status in {
            BatchAssessment.Status.COMPLETE,
            BatchAssessment.Status.CANCELLED,
        }:
            batch.upload_payload = b""
            batch.save(update_fields=["upload_payload"])
    return batch


def _legacy_results(batch: BatchAssessment) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in batch.rows.select_related("case").all():
        item = {
            "row": row.row_number,
            "applicant_reference": row.applicant_reference,
            "status": row.status,
            "warnings": row.warnings,
            "errors": row.errors,
        }
        item.update(row.result)
        output.append(item)
    return output


def _finalize_batch(batch: BatchAssessment, *, worker_token: uuid.UUID) -> BatchAssessment:
    with transaction.atomic():
        locked = BatchAssessment.objects.select_for_update().get(id=batch.id)
        if (
            locked.status != BatchAssessment.Status.PROCESSING
            or locked.worker_token != worker_token
        ):
            raise RuntimeError("Batch processing lease was lost before finalization.")
        counts = {
            status: locked.rows.filter(status=status).count()
            for status in BatchRow.Status.values
        }
        locked.valid_rows = counts[BatchRow.Status.SCORED]
        locked.invalid_rows = (
            counts[BatchRow.Status.INVALID] + counts[BatchRow.Status.FAILED]
        )
        locked.results = _legacy_results(locked)
        locked.status = BatchAssessment.Status.COMPLETE
        locked.completed_at = timezone.now()
        locked.worker_token = None
        locked.save(
            update_fields=[
                "valid_rows",
                "invalid_rows",
                "results",
                "status",
                "completed_at",
                "worker_token",
            ]
        )
    return locked


def recover_stale_batches() -> int:
    """Return abandoned leases to the queue, bounded by the retry policy."""
    from django.conf import settings

    cutoff = timezone.now() - timedelta(seconds=settings.BATCH_LEASE_SECONDS)
    stale_ids = BatchAssessment.objects.filter(
        status=BatchAssessment.Status.PROCESSING,
    ).filter(Q(heartbeat_at__lt=cutoff) | Q(heartbeat_at__isnull=True)).values_list(
        "id", flat=True
    )
    recovered = 0
    for batch_id in stale_ids.iterator():
        with transaction.atomic():
            batch = BatchAssessment.objects.select_for_update().filter(
                id=batch_id,
                status=BatchAssessment.Status.PROCESSING,
            ).first()
            if batch is None or (batch.heartbeat_at and batch.heartbeat_at >= cutoff):
                continue
            batch.worker_token = None
            if batch.attempts >= settings.BATCH_MAX_ATTEMPTS:
                batch.status = BatchAssessment.Status.FAILED
                batch.error_message = (
                    "Worker lease expired and the automatic retry limit was reached."
                )
                batch.completed_at = timezone.now()
                batch.save(
                    update_fields=[
                        "worker_token",
                        "status",
                        "error_message",
                        "completed_at",
                    ]
                )
            else:
                batch.status = BatchAssessment.Status.PENDING
                batch.error_message = (
                    "Worker lease expired; the batch was safely returned to the queue."
                )
                batch.save(update_fields=["worker_token", "status", "error_message"])
            recovered += 1
    return recovered
