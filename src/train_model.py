from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import sklearn
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.frozen import FrozenEstimator
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    ConfusionMatrixDisplay,
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import GridSearchCV, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .model_reporting import (
    save_age_fairness_report,
    save_bootstrap_intervals,
    save_calibration_report,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "data" / "credit_risk.csv"
MODELS_DIR = PROJECT_ROOT / "models"
REPORTS_DIR = PROJECT_ROOT / "reports"
MODEL_BUNDLE_PATH = MODELS_DIR / "credit_risk_model.pkl"
MODEL_MANIFEST_PATH = MODELS_DIR / "model_manifest.json"

RANDOM_STATE = 42
TARGET = "loan_status"
MODEL_VERSION = "2.0.0"
FALSE_NEGATIVE_COST = 5
FALSE_POSITIVE_COST = 1

NUMERIC_FEATURES = [
    "person_income",
    "person_emp_length",
    "loan_amnt",
    "loan_percent_income",
    "cb_person_cred_hist_length",
]

CATEGORICAL_FEATURES = [
    "person_home_ownership",
    "loan_intent",
    "cb_person_default_on_file",
]

FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
EXCLUDED_LENDER_ASSIGNED_FEATURES = ["loan_int_rate", "loan_grade"]
EXCLUDED_POLICY_FEATURES = ["person_age"]
FORM_NUMERIC_FEATURES = ["person_age"] + NUMERIC_FEATURES


def _one_hot_encoder() -> OneHotEncoder:
    try:
        return OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    except TypeError:
        return OneHotEncoder(handle_unknown="ignore", sparse=False)


def load_credit_data(path: Path = DATA_PATH) -> pd.DataFrame:
    data = pd.read_csv(path)
    data = data.drop_duplicates().copy()

    # Extremely long employment values are data-quality issues in this dataset.
    data.loc[data["person_emp_length"] > 60, "person_emp_length"] = np.nan
    data.loc[data["person_age"] > 100, "person_age"] = np.nan

    return data


def build_preprocessor() -> ColumnTransformer:
    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )

    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("encoder", _one_hot_encoder()),
        ]
    )

    return ColumnTransformer(
        transformers=[
            ("numeric", numeric_pipeline, NUMERIC_FEATURES),
            ("categorical", categorical_pipeline, CATEGORICAL_FEATURES),
        ],
        remainder="drop",
    )


def make_pipeline(classifier: Any) -> Pipeline:
    return Pipeline(
        steps=[
            ("preprocessor", build_preprocessor()),
            ("classifier", classifier),
        ]
    )


def build_candidate_models() -> dict[str, Pipeline]:
    return {
        "Logistic Regression": make_pipeline(
            LogisticRegression(max_iter=1000, class_weight="balanced")
        ),
        "Random Forest": make_pipeline(
            RandomForestClassifier(
                n_estimators=200,
                random_state=RANDOM_STATE,
                class_weight="balanced",
                n_jobs=-1,
            )
        ),
        "Gradient Boosting": make_pipeline(
            GradientBoostingClassifier(random_state=RANDOM_STATE)
        ),
    }


def evaluate_predictions(
    y_true: pd.Series,
    y_probability: np.ndarray,
    threshold: float = 0.5,
) -> dict[str, float]:
    y_pred = (y_probability >= threshold).astype(int)
    return {
        "accuracy": accuracy_score(y_true, y_pred),
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred, zero_division=0),
        "f1_score": f1_score(y_true, y_pred, zero_division=0),
        "roc_auc": roc_auc_score(y_true, y_probability),
        "average_precision": average_precision_score(y_true, y_probability),
        "brier_score": brier_score_loss(y_true, y_probability),
    }


def evaluate_model(
    name: str,
    model: Pipeline,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    threshold: float = 0.5,
) -> dict[str, float | str]:
    probabilities = model.predict_proba(X_test)[:, 1]
    metrics = evaluate_predictions(y_test, probabilities, threshold)
    return {"model": name, **metrics}


def tune_random_forest(X_train: pd.DataFrame, y_train: pd.Series, quick: bool) -> GridSearchCV:
    param_grid = {
        "classifier__n_estimators": [200] if quick else [200, 300],
        "classifier__max_depth": [None, 16] if quick else [None, 16, 24],
        "classifier__min_samples_leaf": [1, 2],
    }

    search = GridSearchCV(
        estimator=make_pipeline(
            RandomForestClassifier(
                random_state=RANDOM_STATE,
                class_weight="balanced",
                n_jobs=-1,
            )
        ),
        param_grid=param_grid,
        cv=3,
        scoring="f1",
        n_jobs=-1,
        verbose=0,
    )
    search.fit(X_train, y_train)
    return search


def build_threshold_table(
    y_true: pd.Series,
    y_probability: np.ndarray,
    false_negative_cost: int = FALSE_NEGATIVE_COST,
    false_positive_cost: int = FALSE_POSITIVE_COST,
) -> pd.DataFrame:
    rows = []
    for threshold in np.round(np.arange(0.10, 0.91, 0.01), 2):
        y_pred = (y_probability >= threshold).astype(int)
        tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
        rows.append(
            {
                "threshold": threshold,
                "accuracy": accuracy_score(y_true, y_pred),
                "precision": precision_score(y_true, y_pred, zero_division=0),
                "recall": recall_score(y_true, y_pred, zero_division=0),
                "f1_score": f1_score(y_true, y_pred, zero_division=0),
                "true_negatives": tn,
                "false_positives": fp,
                "false_negatives": fn,
                "true_positives": tp,
                "business_cost": (false_negative_cost * fn) + (false_positive_cost * fp),
            }
        )

    return pd.DataFrame(rows)


def choose_business_threshold(threshold_table: pd.DataFrame) -> float:
    ranked = threshold_table.sort_values(
        ["business_cost", "f1_score", "recall"],
        ascending=[True, False, False],
    )
    return float(ranked.iloc[0]["threshold"])


def build_feature_reference(data: pd.DataFrame) -> dict[str, Any]:
    return {
        "numeric_medians": {
            column: float(data[column].median()) for column in FORM_NUMERIC_FEATURES
        },
        "categorical_modes": {
            column: str(data[column].mode(dropna=True).iloc[0])
            for column in CATEGORICAL_FEATURES
        },
        "categorical_options": {
            column: sorted(data[column].dropna().astype(str).unique().tolist())
            for column in CATEGORICAL_FEATURES
        },
        "numeric_bounds": {
            column: {
                "minimum": float(data[column].quantile(0.005)),
                "maximum": float(data[column].quantile(0.995)),
            }
            for column in FORM_NUMERIC_FEATURES
        },
    }


def build_drift_reference(data: pd.DataFrame) -> dict[str, Any]:
    numeric: dict[str, Any] = {}
    for column in NUMERIC_FEATURES:
        values = data[column].dropna().astype(float)
        edges = np.unique(values.quantile(np.linspace(0, 1, 11)).to_numpy())
        if len(edges) < 3:
            edges = np.array([-np.inf, values.median(), np.inf])
        else:
            edges[0] = -np.inf
            edges[-1] = np.inf
        counts, _ = np.histogram(values, bins=edges)
        proportions = (counts / counts.sum()).tolist()
        numeric[column] = {
            "edges": edges.tolist(),
            "proportions": proportions,
        }

    categorical = {
        column: data[column].fillna("__MISSING__").astype(str).value_counts(normalize=True).to_dict()
        for column in CATEGORICAL_FEATURES
    }
    return {
        "numeric": numeric,
        "categorical": categorical,
        "observed_default_rate": float(data[TARGET].mean()),
    }


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def git_is_dirty() -> bool | None:
    try:
        status = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=PROJECT_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return bool(status.strip())
    except (OSError, subprocess.SubprocessError):
        return None


def save_model_comparison_chart(results: pd.DataFrame) -> None:
    chart_data = results.set_index("model")[["accuracy", "precision", "recall", "f1_score", "roc_auc"]]
    ax = chart_data.plot(kind="bar", figsize=(11, 6), ylim=(0, 1), rot=0)
    ax.set_title("Model Performance Comparison")
    ax.set_ylabel("Score")
    ax.set_xlabel("")
    ax.legend(loc="lower right")
    plt.tight_layout()
    plt.savefig(REPORTS_DIR / "model_comparison.png", dpi=160)
    plt.close()


def save_confusion_matrix_chart(
    y_test: pd.Series,
    y_probability: np.ndarray,
    threshold: float,
) -> None:
    y_pred = (y_probability >= threshold).astype(int)
    cm = confusion_matrix(y_test, y_pred)
    display = ConfusionMatrixDisplay(
        confusion_matrix=cm,
        display_labels=["Non-default", "Default"],
    )
    display.plot(cmap="Blues", values_format="d")
    plt.title(f"Confusion Matrix at Business Threshold ({threshold:.2f})")
    plt.tight_layout()
    plt.savefig(REPORTS_DIR / "confusion_matrix.png", dpi=160)
    plt.close()


def save_threshold_chart(threshold_table: pd.DataFrame) -> None:
    fig, ax1 = plt.subplots(figsize=(11, 6))
    ax1.plot(threshold_table["threshold"], threshold_table["precision"], label="Precision")
    ax1.plot(threshold_table["threshold"], threshold_table["recall"], label="Recall")
    ax1.plot(threshold_table["threshold"], threshold_table["f1_score"], label="F1-score")
    ax1.set_xlabel("Decision Threshold")
    ax1.set_ylabel("Metric")
    ax1.set_ylim(0, 1)

    ax2 = ax1.twinx()
    ax2.plot(
        threshold_table["threshold"],
        threshold_table["business_cost"],
        color="#7a3e00",
        linestyle="--",
        label="Business Cost",
    )
    ax2.set_ylabel("Business Cost")

    lines, labels = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines + lines2, labels + labels2, loc="center right")
    plt.title("Threshold Tradeoff: Risk Capture vs Customer Rejection")
    plt.tight_layout()
    plt.savefig(REPORTS_DIR / "threshold_tradeoff.png", dpi=160)
    plt.close(fig)


def save_permutation_importance(
    model: Pipeline,
    X_test: pd.DataFrame,
    y_test: pd.Series,
) -> pd.DataFrame:
    sample_size = min(3000, len(X_test))
    X_sample = X_test.sample(sample_size, random_state=RANDOM_STATE)
    y_sample = y_test.loc[X_sample.index]

    result = permutation_importance(
        model,
        X_sample,
        y_sample,
        scoring="f1",
        n_repeats=7,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    importance = (
        pd.DataFrame(
            {
                "feature": X_sample.columns,
                "importance_mean": result.importances_mean,
                "importance_std": result.importances_std,
            }
        )
        .sort_values("importance_mean", ascending=False)
        .reset_index(drop=True)
    )
    importance.to_csv(REPORTS_DIR / "permutation_importance.csv", index=False)

    top = importance.head(10).sort_values("importance_mean")
    plt.figure(figsize=(10, 6))
    plt.barh(top["feature"], top["importance_mean"], xerr=top["importance_std"])
    plt.title("Top Drivers of Credit Default Predictions")
    plt.xlabel("Permutation Importance (F1 decrease)")
    plt.tight_layout()
    plt.savefig(REPORTS_DIR / "permutation_importance.png", dpi=160)
    plt.close()

    return importance


def write_business_report(
    final_metrics: dict[str, float],
    business_metrics: dict[str, float],
    threshold: float,
    grid_search: GridSearchCV,
    threshold_row: pd.Series,
    split_sizes: dict[str, int],
) -> None:
    report = f"""# BankRisk Compass Final Report

## Final Model

The final model is a calibrated, leakage-safe Random Forest classifier. Missing values, scaling, and one-hot encoding are fitted only on training data. Probability calibration and the business threshold are selected on a separate validation set; the final metrics below are measured once on an untouched test set.

Application-time scoring intentionally excludes lender-assigned fields (`loan_grade` and `loan_int_rate`) to avoid using information that may not exist when an applicant is first assessed.
Age is also excluded from the probability model; it is retained only for input plausibility checks and subgroup monitoring.

Data split:

- Training: {split_sizes["train"]:,} rows
- Validation/calibration: {split_sizes["validation"]:,} rows
- Final test: {split_sizes["test"]:,} rows

Best hyperparameters:

```text
{grid_search.best_params_}
```

## Default 0.50 Threshold Results

| Metric | Score |
|---|---:|
| Accuracy | {final_metrics["accuracy"]:.3f} |
| Precision | {final_metrics["precision"]:.3f} |
| Recall | {final_metrics["recall"]:.3f} |
| F1-score | {final_metrics["f1_score"]:.3f} |
| ROC-AUC | {final_metrics["roc_auc"]:.3f} |
| Average precision | {final_metrics["average_precision"]:.3f} |
| Brier score | {final_metrics["brier_score"]:.3f} |

## Business Threshold Results

The selected business threshold is **{threshold:.2f}**. It assumes a false negative is 5x more costly than a false positive:

- False negative: a risky borrower is approved.
- False positive: a safer borrower is rejected or sent to manual review.

| Metric | Score |
|---|---:|
| Accuracy | {business_metrics["accuracy"]:.3f} |
| Precision | {business_metrics["precision"]:.3f} |
| Recall | {business_metrics["recall"]:.3f} |
| F1-score | {business_metrics["f1_score"]:.3f} |
| ROC-AUC | {business_metrics["roc_auc"]:.3f} |
| Average precision | {business_metrics["average_precision"]:.3f} |
| Brier score | {business_metrics["brier_score"]:.3f} |
| False positives | {int(threshold_row["false_positives"])} |
| False negatives | {int(threshold_row["false_negatives"])} |
| Business cost | {int(threshold_row["business_cost"])} |

## Interpretation

The model is a decision-support tool, not an autonomous approval system. The business threshold prioritizes recall for defaults while monitoring the number of safer applicants routed to review. Age-group diagnostics and calibration reports are generated for governance review, but they do not replace a complete fair-lending assessment using legally appropriate protected-class data.
"""
    (REPORTS_DIR / "business_report.md").write_text(report, encoding="utf-8")


def train_and_save(quick: bool = False) -> dict[str, Any]:
    MODELS_DIR.mkdir(exist_ok=True)
    REPORTS_DIR.mkdir(exist_ok=True)

    data = load_credit_data()
    X = data[FEATURES]
    y = data[TARGET]

    X_development, X_test, y_development, y_test = train_test_split(
        X,
        y,
        test_size=0.20,
        random_state=RANDOM_STATE,
        stratify=y,
    )
    X_train, X_validation, y_train, y_validation = train_test_split(
        X_development,
        y_development,
        test_size=0.25,
        random_state=RANDOM_STATE,
        stratify=y_development,
    )

    model_results = []
    for name, model in build_candidate_models().items():
        model.fit(X_train, y_train)
        result = evaluate_model(name, model, X_validation, y_validation)
        result["evaluation_split"] = "validation"
        model_results.append(result)

    results = pd.DataFrame(model_results).sort_values("f1_score", ascending=False)
    results.to_csv(REPORTS_DIR / "model_comparison.csv", index=False)
    save_model_comparison_chart(results)

    grid_search = tune_random_forest(X_train, y_train, quick=quick)
    explanation_pipeline = grid_search.best_estimator_
    calibrated_model = CalibratedClassifierCV(
        FrozenEstimator(explanation_pipeline),
        method="sigmoid",
    )
    calibrated_model.fit(X_validation, y_validation)

    validation_probability = calibrated_model.predict_proba(X_validation)[:, 1]
    validation_threshold_table = build_threshold_table(
        y_validation,
        validation_probability,
    )
    business_threshold = choose_business_threshold(validation_threshold_table)

    final_probability = calibrated_model.predict_proba(X_test)[:, 1]
    final_metrics = evaluate_predictions(y_test, final_probability, threshold=0.5)
    threshold_table = build_threshold_table(y_test, final_probability)
    business_metrics = evaluate_predictions(
        y_test,
        final_probability,
        threshold=business_threshold,
    )
    threshold_row = threshold_table.iloc[
        (threshold_table["threshold"] - business_threshold).abs().argsort()[:1]
    ].iloc[0]

    threshold_table.to_csv(REPORTS_DIR / "threshold_analysis.csv", index=False)
    validation_threshold_table.to_csv(
        REPORTS_DIR / "threshold_selection_validation.csv",
        index=False,
    )
    pd.DataFrame(
        [
            {
                "model": "Random Forest",
                "evaluation_split": "final_test",
                "decision_threshold": 0.5,
                **final_metrics,
            },
            {
                "model": "Random Forest",
                "evaluation_split": "final_test",
                "decision_threshold": business_threshold,
                **business_metrics,
            },
        ]
    ).to_csv(REPORTS_DIR / "final_model_metrics.csv", index=False)

    final_pred = (final_probability >= business_threshold).astype(int)
    (REPORTS_DIR / "classification_report.txt").write_text(
        classification_report(
            y_test,
            final_pred,
            target_names=["Non-default", "Default"],
            digits=3,
        ),
        encoding="utf-8",
    )

    save_confusion_matrix_chart(y_test, final_probability, business_threshold)
    save_threshold_chart(threshold_table)
    permutation = save_permutation_importance(explanation_pipeline, X_test, y_test)
    calibration = save_calibration_report(
        y_test,
        final_probability,
        REPORTS_DIR,
    )
    fairness = save_age_fairness_report(
        data,
        y_test,
        final_probability,
        business_threshold,
        REPORTS_DIR,
    )
    confidence_intervals = save_bootstrap_intervals(
        y_test,
        final_probability,
        business_threshold,
        REPORTS_DIR,
        iterations=200 if quick else 1000,
    )
    split_sizes = {
        "train": len(X_train),
        "validation": len(X_validation),
        "test": len(X_test),
    }
    write_business_report(
        final_metrics,
        business_metrics,
        business_threshold,
        grid_search,
        threshold_row,
        split_sizes,
    )

    bundle = {
        "pipeline": explanation_pipeline,
        "predictor": calibrated_model,
        "threshold": business_threshold,
        "default_threshold_metrics": final_metrics,
        "business_threshold_metrics": business_metrics,
        "best_params": grid_search.best_params_,
        "features": FEATURES,
        "numeric_features": NUMERIC_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "target": TARGET,
        "feature_reference": build_feature_reference(data),
        "drift_reference": build_drift_reference(data),
        "permutation_importance": permutation,
        "calibration_analysis": calibration,
        "fairness_age_groups": fairness,
        "metric_confidence_intervals": confidence_intervals,
        "excluded_lender_assigned_features": EXCLUDED_LENDER_ASSIGNED_FEATURES,
        "excluded_policy_features": EXCLUDED_POLICY_FEATURES,
        "model_version": MODEL_VERSION,
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_sha256": file_sha256(DATA_PATH),
        "git_commit": git_commit(),
        "git_dirty": git_is_dirty(),
        "split_sizes": split_sizes,
        "cost_assumptions": {
            "false_negative": FALSE_NEGATIVE_COST,
            "false_positive": FALSE_POSITIVE_COST,
        },
        "runtime_versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__,
        },
        "risk_bands": {
            "low": round(max(0.05, business_threshold * 0.5), 2),
            "medium": business_threshold,
        },
    }

    joblib.dump(bundle, MODEL_BUNDLE_PATH, compress=3)
    MODEL_MANIFEST_PATH.write_text(
        json.dumps(
            {
                "model_version": MODEL_VERSION,
                "trained_at_utc": bundle["trained_at_utc"],
                "model_sha256": file_sha256(MODEL_BUNDLE_PATH),
                "data_sha256": bundle["data_sha256"],
                "git_commit": bundle["git_commit"],
                "git_dirty": bundle["git_dirty"],
                "features": FEATURES,
                "excluded_lender_assigned_features": EXCLUDED_LENDER_ASSIGNED_FEATURES,
                "excluded_policy_features": EXCLUDED_POLICY_FEATURES,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return {
        "model_path": str(MODEL_BUNDLE_PATH),
        "model_comparison": results,
        "default_metrics": final_metrics,
        "business_metrics": business_metrics,
        "business_threshold": business_threshold,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the BankRisk Compass model.")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Use a smaller hyperparameter grid for faster local iteration.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    output = train_and_save(quick=args.quick)
    print(f"Saved model bundle: {output['model_path']}")
    print(f"Business threshold: {output['business_threshold']:.2f}")
    print("Default-threshold metrics:")
    for metric, value in output["default_metrics"].items():
        print(f"  {metric}: {value:.3f}")
