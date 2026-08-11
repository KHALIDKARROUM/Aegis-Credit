from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from app import services
from app.models import CaseOutcome, MonitoringRun
from src.feature_contract import FeatureContractError, model_feature_frame
from src.monitor_model import build_drift_report
from src.release_artifacts import file_sha256


class Command(BaseCommand):
    help = "Recompute and persist a traceable drift/performance monitoring run."

    def add_arguments(self, parser):
        parser.add_argument("input_data", help="Representative raw application CSV for the window.")
        parser.add_argument("--window-start", required=True)
        parser.add_argument("--window-end", required=True)
        parser.add_argument("--as-of", required=True)
        parser.add_argument("--owner", required=True)
        parser.add_argument("--confirm", action="store_true")

    def handle(self, *args, **options):
        path = Path(options["input_data"]).resolve()
        if not path.is_file():
            raise CommandError(f"Monitoring input not found: {path}")
        try:
            raw = pd.read_csv(path)
            incoming = model_feature_frame(raw)
            bundle = services.load_model_bundle()
        except (OSError, ValueError, FeatureContractError, services.ArtifactIntegrityError) as exc:
            raise CommandError(f"Monitoring input or active release is invalid: {exc}") from exc
        minimum_sample = settings.MONITORING_MIN_SAMPLE_SIZE
        if len(incoming) < minimum_sample:
            raise CommandError(
                f"Monitoring windows require at least {minimum_sample:,} valid rows; "
                f"received {len(incoming):,}."
            )
        manifest = services.load_model_manifest()
        metadata = {
            "dataset_sha256": file_sha256(path),
            "rows": len(incoming),
            "model_version": str(bundle.get("model_version", "legacy")),
            "model_sha256": str(manifest.get("model_sha256", "unavailable")),
        }
        frame = build_drift_report(
            incoming,
            bundle,
            dataset=str(path),
            dataset_sha256=metadata["dataset_sha256"],
            model_sha256=metadata["model_sha256"],
        )
        try:
            window_start = date.fromisoformat(options["window_start"])
            window_end = date.fromisoformat(options["window_end"])
            as_of = date.fromisoformat(options["as_of"])
        except ValueError as exc:
            raise CommandError("Window and as-of dates must use YYYY-MM-DD.") from exc
        if not window_start <= window_end <= as_of:
            raise CommandError("Dates must satisfy window-start <= window-end <= as-of.")

        alerts = frame[frame["status"].astype(str).str.lower().eq("drift")][
            ["feature", "status", "drift_score"]
        ].to_dict("records")
        watches = frame[frame["status"].astype(str).str.lower().eq("watch")][
            ["feature", "status", "drift_score"]
        ].to_dict("records")
        outcome_queryset = CaseOutcome.objects.filter(
            case__model_version=metadata["model_version"],
            as_of_date__lte=as_of,
        ).select_related("case")
        mature_outcome_count = outcome_queryset.exclude(
            outcome=CaseOutcome.Outcome.CLOSED_OTHER
        ).count()
        performance = services.outcome_performance_table(outcome_queryset)
        self.stdout.write(
            f"Recomputed {len(frame)} drift rows, {len(alerts)} alerts, "
            f"{len(watches)} watches, and "
            f"{mature_outcome_count} mature outcomes."
        )
        if not options["confirm"]:
            self.stdout.write("Dry run only. Add --confirm to persist this monitoring run.")
            return
        sanitized = frame.where(pd.notna(frame), None).to_dict("records")
        performance_rows = performance.where(pd.notna(performance), None).to_dict("records")
        run = MonitoringRun.objects.create(
            as_of_date=as_of,
            window_start=window_start,
            window_end=window_end,
            model_version=metadata["model_version"],
            model_release_id=metadata["model_sha256"],
            sample_size=int(float(metadata["rows"])),
            mature_outcome_count=mature_outcome_count,
            status=MonitoringRun.Status.ALERT if alerts else MonitoringRun.Status.PASS,
            metrics={
                "drift_rows": sanitized,
                "performance_rows": performance_rows,
                "watch_rows": watches,
                "computation": "recomputed_from_digest_bound_raw_input",
            },
            alerts=alerts,
            input_digest=metadata["dataset_sha256"],
            owner=options["owner"].strip(),
        )
        self.stdout.write(self.style.SUCCESS(f"Recorded monitoring run {run.id}."))
