from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from .train_model import MODEL_BUNDLE_PATH, REPORTS_DIR


def _status(value: float) -> str:
    if value >= 0.25:
        return "drift"
    if value >= 0.10:
        return "watch"
    return "stable"


def population_stability_index(
    values: pd.Series,
    edges: list[float],
    expected: list[float],
) -> float:
    clean = values.dropna().astype(float)
    actual_counts, _ = np.histogram(clean, bins=np.asarray(edges, dtype=float))
    actual = actual_counts / max(actual_counts.sum(), 1)
    expected_array = np.asarray(expected, dtype=float)
    actual = np.clip(actual, 1e-6, None)
    expected_array = np.clip(expected_array, 1e-6, None)
    return float(np.sum((actual - expected_array) * np.log(actual / expected_array)))


def build_drift_report(data: pd.DataFrame, bundle: dict[str, Any]) -> pd.DataFrame:
    reference = bundle["drift_reference"]
    rows: list[dict[str, Any]] = []

    for feature, baseline in reference["numeric"].items():
        value = population_stability_index(
            data[feature],
            baseline["edges"],
            baseline["proportions"],
        )
        rows.append(
            {
                "feature": feature,
                "feature_type": "numeric",
                "drift_score": value,
                "status": _status(value),
            }
        )

    for feature, expected in reference["categorical"].items():
        actual = data[feature].fillna("__MISSING__").astype(str).value_counts(normalize=True).to_dict()
        categories = set(expected) | set(actual)
        total_variation = 0.5 * sum(
            abs(float(actual.get(category, 0.0)) - float(expected.get(category, 0.0)))
            for category in categories
        )
        rows.append(
            {
                "feature": feature,
                "feature_type": "categorical",
                "drift_score": total_variation,
                "status": _status(total_variation),
            }
        )

    return pd.DataFrame(rows).sort_values("drift_score", ascending=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare new applicant data with the training baseline.")
    parser.add_argument("--data", type=Path, required=True, help="CSV containing model input columns.")
    parser.add_argument(
        "--output",
        type=Path,
        default=REPORTS_DIR / "drift_monitoring.csv",
        help="Destination CSV report.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    model_bundle = joblib.load(MODEL_BUNDLE_PATH)
    incoming = pd.read_csv(args.data)
    report = build_drift_report(incoming, model_bundle)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(args.output, index=False)
    print(report.to_string(index=False))
    print(f"Saved drift report: {args.output}")
