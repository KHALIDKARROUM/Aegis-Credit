from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .feature_contract import (
    FeatureContractError,
    TARGET,
    model_feature_frame,
    validate_binary_target,
    validate_categorical_contract,
)
from .release_artifacts import (
    ArtifactIntegrityError,
    file_sha256,
    load_verified_model_artifact,
)
from .train_model import evaluate_predictions


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_BUNDLE_PATH = PROJECT_ROOT / "models" / "credit_risk_model.pkl"
MODEL_MANIFEST_PATH = PROJECT_ROOT / "models" / "model_manifest.json"
REPORTS_DIR = PROJECT_ROOT / "reports"


def evaluate_external_data(
    data: pd.DataFrame,
    bundle: dict[str, Any],
    *,
    label: str = TARGET,
) -> dict[str, float]:
    if label not in data.columns:
        raise ValueError(f"Validation data is missing outcome column: {label}")
    application = model_feature_frame(data)
    options = bundle.get("feature_reference", {}).get("categorical_options", {})
    if options:
        validate_categorical_contract(application, options)
    outcomes = validate_binary_target(data[label], name=label)
    predictor = bundle.get("predictor")
    if predictor is None:
        predictor = bundle["pipeline"]
    probabilities = predictor.predict_proba(application)[:, 1]
    return evaluate_predictions(
        outcomes,
        probabilities,
        threshold=float(bundle["threshold"]),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate a verified model on external or out-of-time mature outcomes."
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
        data_path = args.data.resolve()
        data = pd.read_csv(data_path)
        metrics = evaluate_external_data(data, verified.bundle, label=args.label)
    except (ArtifactIntegrityError, FeatureContractError, FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    output = pd.DataFrame(
        [
            {
                "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
                "model_version": verified.bundle["model_version"],
                "model_sha256": verified.model_sha256,
                "signed_release": verified.signed_release,
                "dataset": str(data_path),
                "dataset_sha256": file_sha256(data_path),
                "rows": len(data),
                "observed_default_rate": float(data[args.label].mean()),
                "threshold": verified.bundle["threshold"],
                **metrics,
            }
        ]
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(args.output, index=False)
    print(output.to_string(index=False))
    print(f"Saved external validation report: {args.output}")
