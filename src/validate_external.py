from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd

from .train_model import (
    MODEL_BUNDLE_PATH,
    MODEL_MANIFEST_PATH,
    REPORTS_DIR,
    TARGET,
    evaluate_predictions,
    file_sha256,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate the saved model on an external or out-of-time labeled dataset."
    )
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPORTS_DIR / "external_validation.csv",
    )
    parser.add_argument(
        "--label",
        default=TARGET,
        help="Name of the mature binary outcome column.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    manifest = json.loads(MODEL_MANIFEST_PATH.read_text(encoding="utf-8"))
    if file_sha256(MODEL_BUNDLE_PATH) != manifest.get("model_sha256"):
        raise SystemExit("Model integrity verification failed.")

    bundle = joblib.load(MODEL_BUNDLE_PATH)
    data = pd.read_csv(args.data)
    required = set(bundle["features"]) | {args.label}
    missing = sorted(required - set(data.columns))
    if missing:
        raise SystemExit(f"Validation data is missing columns: {', '.join(missing)}")

    probabilities = bundle["predictor"].predict_proba(data[bundle["features"]])[:, 1]
    metrics = evaluate_predictions(
        data[args.label],
        probabilities,
        threshold=float(bundle["threshold"]),
    )
    output = pd.DataFrame(
        [
            {
                "model_version": bundle["model_version"],
                "dataset": str(args.data),
                "rows": len(data),
                "threshold": bundle["threshold"],
                **metrics,
            }
        ]
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(args.output, index=False)
    print(output.to_string(index=False))
    print(f"Saved external validation report: {args.output}")
