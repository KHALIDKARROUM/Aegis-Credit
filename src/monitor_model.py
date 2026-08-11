from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .feature_contract import FeatureContractError, model_feature_frame
from .release_artifacts import (
    ArtifactIntegrityError,
    file_sha256,
    load_verified_model_artifact,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_BUNDLE_PATH = PROJECT_ROOT / "models" / "credit_risk_model.pkl"
MODEL_MANIFEST_PATH = PROJECT_ROOT / "models" / "model_manifest.json"
REPORTS_DIR = PROJECT_ROOT / "reports"

_STATUS_RANK = {"unavailable": -1, "stable": 0, "watch": 1, "drift": 2}


def _distribution_status(value: float) -> str:
    if not np.isfinite(value):
        return "unavailable"
    if value >= 0.25:
        return "drift"
    if value >= 0.10:
        return "watch"
    return "stable"


def _rate_status(absolute_change: float) -> str:
    """Classify an absolute missing/unknown-rate change in percentage points."""

    if not np.isfinite(absolute_change):
        return "unavailable"
    if absolute_change >= 0.05:
        return "drift"
    if absolute_change >= 0.02:
        return "watch"
    return "stable"


def _worst_status(*statuses: str) -> str:
    return max(statuses, key=lambda status: _STATUS_RANK[status])


def population_stability_index(
    values: pd.Series,
    edges: list[float],
    expected: list[float],
) -> float:
    clean = values.dropna().astype(float)
    if clean.empty:
        return float("nan")
    actual_counts, _ = np.histogram(clean, bins=np.asarray(edges, dtype=float))
    actual = actual_counts / actual_counts.sum()
    expected_array = np.asarray(expected, dtype=float)
    actual = np.clip(actual, 1e-6, None)
    expected_array = np.clip(expected_array, 1e-6, None)
    return float(np.sum((actual - expected_array) * np.log(actual / expected_array)))


def build_drift_report(
    data: pd.DataFrame,
    bundle: dict[str, Any],
    *,
    dataset: str = "unspecified",
    dataset_sha256: str = "unavailable",
    model_sha256: str = "unavailable",
    generated_at_utc: str | None = None,
) -> pd.DataFrame:
    reference = bundle["drift_reference"]
    generated_at = generated_at_utc or datetime.now(timezone.utc).isoformat()
    metadata = {
        "generated_at_utc": generated_at,
        "dataset": dataset,
        "dataset_sha256": dataset_sha256,
        "rows": int(len(data)),
        "reference_rows": int(reference.get("reference_rows", 0)),
        "model_version": str(bundle.get("model_version", "legacy")),
        "model_sha256": model_sha256,
    }
    rows: list[dict[str, Any]] = []

    for feature, baseline in reference["numeric"].items():
        distribution_score = population_stability_index(
            data[feature],
            baseline["edges"],
            baseline["proportions"],
        )
        actual_missing_rate = float(data[feature].isna().mean())
        expected_missing = baseline.get("missing_rate")
        if expected_missing is None:
            missing_delta = float("nan")
            missing_status = "unavailable"
        else:
            missing_delta = abs(actual_missing_rate - float(expected_missing))
            missing_status = _rate_status(missing_delta)
        distribution_status = _distribution_status(distribution_score)
        finite_components = [
            value
            for value in (distribution_score, missing_delta)
            if np.isfinite(value)
        ]
        rows.append(
            {
                **metadata,
                "feature": feature,
                "feature_type": "numeric",
                "drift_score": max(finite_components, default=float("nan")),
                "distribution_drift_score": distribution_score,
                "distribution_status": distribution_status,
                "expected_missing_rate": (
                    float(expected_missing) if expected_missing is not None else float("nan")
                ),
                "actual_missing_rate": actual_missing_rate,
                "missing_rate_delta": missing_delta,
                "missingness_status": missing_status,
                "unknown_category_rate": float("nan"),
                "status": _worst_status(distribution_status, missing_status),
            }
        )

    for feature, expected in reference["categorical"].items():
        actual_series = data[feature].fillna("__MISSING__").astype(str)
        actual = actual_series.value_counts(normalize=True).to_dict()
        categories = set(expected) | set(actual)
        total_variation = 0.5 * sum(
            abs(float(actual.get(category, 0.0)) - float(expected.get(category, 0.0)))
            for category in categories
        )
        expected_missing_rate = float(expected.get("__MISSING__", 0.0))
        actual_missing_rate = float(actual.get("__MISSING__", 0.0))
        missing_delta = abs(actual_missing_rate - expected_missing_rate)
        unknown_rate = float(
            actual_series.isin(set(actual) - set(expected)).mean()
        )
        distribution_status = _distribution_status(total_variation)
        missing_status = _rate_status(missing_delta)
        unknown_status = _rate_status(unknown_rate)
        rows.append(
            {
                **metadata,
                "feature": feature,
                "feature_type": "categorical",
                "drift_score": max(total_variation, missing_delta, unknown_rate),
                "distribution_drift_score": total_variation,
                "distribution_status": distribution_status,
                "expected_missing_rate": expected_missing_rate,
                "actual_missing_rate": actual_missing_rate,
                "missing_rate_delta": missing_delta,
                "missingness_status": missing_status,
                "unknown_category_rate": unknown_rate,
                "status": _worst_status(
                    distribution_status,
                    missing_status,
                    unknown_status,
                ),
            }
        )

    score_reference = bundle.get("score_reference")
    predictor = bundle.get("predictor")
    if score_reference and predictor is not None:
        probabilities = np.asarray(predictor.predict_proba(data)[:, 1], dtype=float)
        score_drift = population_stability_index(
            pd.Series(probabilities),
            score_reference["edges"],
            score_reference["proportions"],
        )
        score_status = _distribution_status(score_drift)
        score_missing_rate = float(np.isnan(probabilities).mean())
        score_missing_status = _rate_status(score_missing_rate)
        rows.append(
            {
                **metadata,
                "feature": "model_score",
                "feature_type": "prediction",
                "drift_score": score_drift,
                "distribution_drift_score": score_drift,
                "distribution_status": score_status,
                "expected_missing_rate": 0.0,
                "actual_missing_rate": score_missing_rate,
                "missing_rate_delta": score_missing_rate,
                "missingness_status": score_missing_status,
                "unknown_category_rate": float("nan"),
                "expected_score_mean": float(score_reference["mean"]),
                "actual_score_mean": float(np.nanmean(probabilities)),
                "status": _worst_status(score_status, score_missing_status),
            }
        )

    report = pd.DataFrame(rows)
    report["_status_rank"] = report["status"].map(_STATUS_RANK)
    return (
        report.sort_values(
            ["_status_rank", "drift_score"],
            ascending=[False, False],
        )
        .drop(columns="_status_rank")
        .reset_index(drop=True)
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare new applicant data with the signed model's training baseline."
    )
    parser.add_argument(
        "--data",
        type=Path,
        required=True,
        help="CSV containing raw application-time input columns.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPORTS_DIR / "drift_monitoring.csv",
        help="Destination CSV report.",
    )
    parser.add_argument(
        "--allow-unsigned-demo",
        action="store_true",
        help="Explicitly allow the hash-checked unsigned demo bundle; never use in production.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        verified = load_verified_model_artifact(
            MODEL_MANIFEST_PATH,
            demo_model_path=MODEL_BUNDLE_PATH,
            allow_unsigned_demo=args.allow_unsigned_demo,
        )
        incoming_path = args.data.resolve()
        incoming_raw = pd.read_csv(incoming_path)
        incoming = model_feature_frame(incoming_raw)
    except (ArtifactIntegrityError, FeatureContractError, FileNotFoundError) as exc:
        raise SystemExit(str(exc)) from exc
    report = build_drift_report(
        incoming,
        verified.bundle,
        dataset=str(incoming_path),
        dataset_sha256=file_sha256(incoming_path),
        model_sha256=verified.model_sha256,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(args.output, index=False)
    print(report.to_string(index=False))
    print(f"Saved drift report: {args.output}")
