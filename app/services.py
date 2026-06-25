from __future__ import annotations

import html
import io
import csv
import hashlib
import json
import logging
from hmac import compare_digest
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "data" / "credit_risk.csv"
MODEL_PATH = PROJECT_ROOT / "models" / "credit_risk_model.pkl"
MODEL_MANIFEST_PATH = PROJECT_ROOT / "models" / "model_manifest.json"
REPORTS_DIR = PROJECT_ROOT / "reports"

REPORT_ARTIFACTS = {
    "business_report.md",
    "classification_report.txt",
    "final_model_metrics.csv",
    "model_comparison.csv",
    "model_comparison.png",
    "permutation_importance.csv",
    "permutation_importance.png",
    "threshold_analysis.csv",
    "threshold_tradeoff.png",
    "confusion_matrix.png",
    "calibration_analysis.csv",
    "calibration_curve.png",
    "fairness_age_groups.csv",
    "threshold_selection_validation.csv",
    "metric_confidence_intervals.csv",
    "drift_monitoring.csv",
}

COLUMN_LABELS = {
    "model": "Model",
    "decision_threshold": "Decision Threshold",
    "threshold": "Threshold",
    "accuracy": "Accuracy",
    "precision": "Precision",
    "recall": "Recall",
    "f1_score": "F1-score",
    "roc_auc": "ROC-AUC",
    "average_precision": "Average Precision",
    "brier_score": "Brier Score",
    "evaluation_split": "Evaluation Split",
    "true_negatives": "True Negatives",
    "false_positives": "False Positives",
    "false_negatives": "False Negatives",
    "true_positives": "True Positives",
    "business_cost": "Business Cost",
    "importance_mean": "Importance Mean",
    "importance_std": "Importance Std.",
}

INTENT_LABELS = {
    "DEBTCONSOLIDATION": "Debt Consol.",
    "EDUCATION": "Education",
    "HOMEIMPROVEMENT": "Home Improve.",
    "MEDICAL": "Medical",
    "PERSONAL": "Personal",
    "VENTURE": "Venture",
}


class ArtifactIntegrityError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@lru_cache(maxsize=1)
def load_model_bundle() -> dict[str, Any]:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            "Model file not found. Run `python -m src.train_model --quick` from the project root first."
        )
    if not MODEL_MANIFEST_PATH.exists():
        raise FileNotFoundError("Model manifest not found. Regenerate the model artifacts.")
    manifest = json.loads(MODEL_MANIFEST_PATH.read_text(encoding="utf-8"))
    expected_hash = str(manifest.get("model_sha256", ""))
    if not expected_hash or not compare_digest(_sha256(MODEL_PATH), expected_hash):
        raise ArtifactIntegrityError("Model artifact integrity verification failed.")

    bundle = joblib.load(MODEL_PATH)
    if str(bundle.get("model_version")) != str(manifest.get("model_version")):
        raise ArtifactIntegrityError("Model version does not match its manifest.")
    return bundle


@lru_cache(maxsize=1)
def load_credit_data() -> pd.DataFrame:
    return pd.read_csv(DATA_PATH)


@lru_cache(maxsize=None)
def load_report_csv(file_name: str) -> pd.DataFrame:
    path = REPORTS_DIR / file_name
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


@lru_cache(maxsize=None)
def load_text_report(file_name: str) -> str:
    path = REPORTS_DIR / file_name
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def predict_default_probability(bundle: dict[str, Any], application: pd.DataFrame) -> float:
    predictor = bundle.get("predictor", bundle["pipeline"])
    return float(predictor.predict_proba(application)[:, 1][0])


def model_metadata(bundle: dict[str, Any]) -> dict[str, str]:
    trained_at = str(bundle.get("trained_at_utc", "Unavailable"))
    if "T" in trained_at:
        trained_at = trained_at.split("T", maxsplit=1)[0]
    revision = str(bundle.get("git_commit", "unavailable"))[:8]
    if bundle.get("git_dirty"):
        revision = f"{revision}+dirty"
    return {
        "version": str(bundle.get("model_version", "legacy")),
        "trained_at": trained_at,
        "git_commit": revision,
    }


def risk_category(probability: float, bundle: dict[str, Any]) -> tuple[str, str, str]:
    low_cutoff = bundle.get("risk_bands", {}).get("low", 0.25)
    medium_cutoff = bundle.get("risk_bands", {}).get("medium", 0.50)

    if probability < low_cutoff:
        return "Low", "low", "#07856a"
    if probability < medium_cutoff:
        return "Medium", "medium", "#f0a500"
    return "High", "high", "#e21f2d"


def format_percent(value: float) -> str:
    return f"{value:.1%}"


def format_score(value: float) -> str:
    return f"{value:.3f}"


def format_money(value: float) -> str:
    return f"${value:,.0f}"


def display_date() -> str:
    today = date.today()
    return f"{today.strftime('%b')} {today.day}, {today.year}"


def pretty_feature_name(feature: str) -> str:
    labels = {
        "loan_grade": "Loan Grade",
        "loan_int_rate": "Interest Rate",
        "loan_percent_income": "Loan % of Income",
        "person_income": "Income",
        "loan_amnt": "Loan Amount",
        "person_home_ownership": "Home Ownership",
        "loan_intent": "Loan Intent",
        "cb_person_default_on_file": "Prior Default",
        "person_emp_length": "Employment Length",
        "person_age": "Age",
        "cb_person_cred_hist_length": "Credit History",
    }
    return labels.get(feature, feature.replace("_", " ").title())


def display_column_name(column: str) -> str:
    return COLUMN_LABELS.get(str(column), str(column).replace("_", " ").title())


def metric_source_row(
    final_metrics: pd.DataFrame,
    threshold_value: float,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    if final_metrics.empty or "decision_threshold" not in final_metrics:
        return fallback.copy()

    matched = final_metrics[
        final_metrics["decision_threshold"].round(2).eq(round(threshold_value, 2))
    ]
    if matched.empty:
        return fallback.copy()

    row = matched.iloc[0].to_dict()
    return {**fallback, **row}


def nearest_threshold_row(threshold_table: pd.DataFrame, threshold: float) -> dict[str, Any]:
    if threshold_table.empty:
        return {}
    index = (threshold_table["threshold"] - threshold).abs().idxmin()
    return threshold_table.loc[index].to_dict()


def dataframe_table(
    frame: pd.DataFrame,
    digits: int = 3,
    max_rows: int | None = None,
) -> dict[str, Any]:
    if frame.empty:
        return {"columns": [], "rows": []}

    working = frame.head(max_rows) if max_rows else frame
    columns = [display_column_name(str(column)) for column in working.columns]
    rows: list[list[str]] = []

    for _, row in working.iterrows():
        cells = []
        for value in row.tolist():
            if isinstance(value, float):
                cells.append(f"{value:.{digits}f}")
            else:
                cells.append(str(value))
        rows.append(cells)

    return {"columns": columns, "rows": rows}


def metric_pairs(row: dict[str, Any], keys: list[tuple[str, str, str]]) -> list[dict[str, str]]:
    pairs = []
    for key, label, formatter in keys:
        value = row.get(key, 0.0)
        if formatter == "percent":
            display_value = format_percent(float(value))
        else:
            display_value = format_score(float(value))
        pairs.append({"label": label, "value": display_value})
    return pairs


def _bar_rows(
    frame: pd.DataFrame,
    label_column: str,
    value_column: str,
    count_column: str | None = None,
    sort_by_value: bool = False,
    label_map: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    if frame.empty:
        return []

    working = frame.copy()
    if sort_by_value:
        working = working.sort_values(value_column)

    rows = []
    for _, row in working.iterrows():
        raw_label = str(row[label_column])
        label = label_map.get(raw_label, raw_label) if label_map else raw_label
        value = float(row[value_column])
        count = int(row[count_column]) if count_column else 0
        rows.append(
            {
                "label": label,
                "full_label": raw_label,
                "value": f"{format_percent(value)} default rate",
                "count": f"n = {count:,}" if count_column else "",
                "width": f"{max(value * 100, 2):.1f}%",
            }
        )
    return rows


def default_rate_by_grade(data: pd.DataFrame) -> list[dict[str, str]]:
    grade = (
        data.groupby("loan_grade", as_index=False)
        .agg(default_rate=("loan_status", "mean"), count=("loan_status", "size"))
    )
    return _bar_rows(grade, "loan_grade", "default_rate", count_column="count")


def default_rate_by_intent(data: pd.DataFrame) -> list[dict[str, str]]:
    intent = (
        data.groupby("loan_intent", as_index=False)
        .agg(default_rate=("loan_status", "mean"), count=("loan_status", "size"))
    )
    return _bar_rows(
        intent,
        "loan_intent",
        "default_rate",
        count_column="count",
        sort_by_value=True,
        label_map=INTENT_LABELS,
    )


def model_comparison_bars(comparison: pd.DataFrame) -> list[dict[str, str]]:
    if comparison.empty:
        return []

    metric_config = [
        ("f1_score", "F1-score", "green"),
        ("roc_auc", "ROC-AUC", "navy"),
        ("accuracy", "Accuracy", "blue"),
    ]
    rows = []
    for _, model_row in comparison.iterrows():
        for metric, label, color in metric_config:
            score = float(model_row.get(metric, 0.0))
            rows.append(
                {
                    "model": str(model_row["model"]),
                    "metric": label,
                    "score": f"{score:.3f}",
                    "width": f"{max(score * 100, 2):.1f}%",
                    "color": color,
                }
            )
    return rows


def importance_bars(importance: pd.DataFrame) -> list[dict[str, str]]:
    if importance.empty:
        return []

    working = importance.head(8).copy()
    working["feature"] = working["feature"].map(pretty_feature_name)
    working = working.sort_values("importance_mean", ascending=False)
    max_value = max(float(working["importance_mean"].max()), 0.001)

    rows = []
    for _, row in working.iterrows():
        value = max(float(row["importance_mean"]), 0.0)
        rows.append(
            {
                "label": str(row["feature"]),
                "value": f"{value:.3f}",
                "width": f"{max((value / max_value) * 100, 2):.1f}%",
            }
        )
    return rows


def get_importance(bundle: dict[str, Any]) -> pd.DataFrame:
    importance = pd.DataFrame(bundle.get("permutation_importance", []))
    if importance.empty:
        importance = load_report_csv("permutation_importance.csv")
    return importance


def dashboard_data() -> dict[str, Any]:
    bundle = load_model_bundle()
    data = load_credit_data()
    comparison = load_report_csv("model_comparison.csv")
    final_metrics = load_report_csv("final_model_metrics.csv")
    threshold_table = load_report_csv("threshold_analysis.csv")
    calibration = load_report_csv("calibration_analysis.csv")
    fairness = load_report_csv("fairness_age_groups.csv")
    importance = get_importance(bundle)

    threshold = float(bundle.get("threshold", 0.5))
    default_metrics = metric_source_row(
        final_metrics,
        0.50,
        {"accuracy": 0.0, "precision": 0.0, "recall": 0.0, "f1_score": 0.0, "roc_auc": 0.0},
    )
    business_metrics = metric_source_row(
        final_metrics,
        threshold,
        {
            "decision_threshold": threshold,
            "accuracy": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "f1_score": 0.0,
            "roc_auc": 0.0,
        },
    )

    if comparison.empty:
        best_model = "Random Forest"
        best_f1 = 0.0
    else:
        best = comparison.sort_values("f1_score", ascending=False).iloc[0]
        best_model = str(best["model"])
        best_f1 = float(best["f1_score"])

    return {
        "bundle": bundle,
        "data": data,
        "comparison": comparison,
        "final_metrics": final_metrics,
        "threshold_table": threshold_table,
        "calibration": calibration,
        "fairness": fairness,
        "importance": importance,
        "threshold": threshold,
        "default_metrics": default_metrics,
        "business_metrics": business_metrics,
        "best_model": best_model,
        "best_f1": best_f1,
    }


def threshold_summary_context(
    threshold_table: pd.DataFrame,
    selected_threshold: float,
    business_threshold: float,
) -> dict[str, Any]:
    row = nearest_threshold_row(threshold_table, selected_threshold)
    selected = float(row.get("threshold", selected_threshold))
    return {
        "row": row,
        "selected_threshold": f"{selected:.2f}",
        "business_threshold": f"{business_threshold:.2f}",
        "current_threshold_label": f"Current selected threshold: {selected:.2f}",
        "business_threshold_label": f"Recommended business threshold: {business_threshold:.2f}",
    }


def application_from_cleaned_data(
    bundle: dict[str, Any],
    cleaned_data: dict[str, Any],
) -> tuple[dict[str, Any], pd.DataFrame]:
    values = dict(cleaned_data)
    income = float(values["person_income"])
    loan_percent_income = float(values["loan_amnt"]) / income
    values["loan_percent_income"] = float(round(loan_percent_income, 4))

    application = pd.DataFrame([values])[bundle["features"]]
    return values, application


def assessment_result(
    bundle: dict[str, Any],
    cleaned_data: dict[str, Any],
    *,
    explain: bool = True,
) -> dict[str, Any]:
    form, application = application_from_cleaned_data(bundle, cleaned_data)
    probability = predict_default_probability(bundle, application)
    category, category_class, category_color = risk_category(probability, bundle)
    threshold = float(bundle.get("threshold", 0.5))
    prediction = "Likely Default" if probability >= threshold else "Likely Non-default"
    if probability >= threshold:
        decision = "Manual review required" if category != "High" else "Enhanced manual review required"
    else:
        decision = "Proceed to standard underwriting"

    snapshot = []
    display_features = ["person_age", *bundle["features"]]
    for feature in display_features:
        value = form[feature]
        if feature == "loan_percent_income":
            display_value = format_percent(float(value))
        elif feature in {"person_income", "loan_amnt"}:
            display_value = format_money(float(value))
        elif isinstance(value, float):
            display_value = f"{value:.2f}"
        else:
            display_value = str(value)
        snapshot.append({"feature": pretty_feature_name(feature), "value": display_value})

    if explain:
        explanation_rows, explanation_method = applicant_explanations(
            bundle,
            application,
            form,
        )
    else:
        explanation_rows = []
        explanation_method = "Explanation omitted for low-latency API scoring."

    return {
        "form": form,
        "application": application,
        "probability": probability,
        "probability_percent": f"{probability:.0%}",
        "gauge_style": f"--score:{probability * 100:.1f}%;--color:{category_color};",
        "category": category,
        "category_class": category_class,
        "category_color": category_color,
        "prediction": prediction,
        "decision": decision,
        "threshold": threshold,
        "snapshot": snapshot,
        "explanation_rows": explanation_rows,
        "explanation_method": explanation_method,
    }


def feature_digest(application: pd.DataFrame) -> str:
    payload = json.dumps(
        application.iloc[0].to_dict(),
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@lru_cache(maxsize=2)
def _tree_explainer(classifier: Any) -> Any:
    import shap

    return shap.TreeExplainer(
        classifier,
        feature_perturbation="tree_path_dependent",
        model_output="raw",
    )


def _source_feature(transformed_name: str, features: list[str]) -> str:
    feature_name = transformed_name.split("__", maxsplit=1)[-1]
    for source in sorted(features, key=len, reverse=True):
        if feature_name == source or feature_name.startswith(f"{source}_"):
            return source
    return feature_name


def _default_class_shap_values(values: Any) -> np.ndarray:
    if isinstance(values, list):
        return np.asarray(values[1])[0]

    array = np.asarray(values)
    if array.ndim == 3:
        return array[0, :, 1]
    if array.ndim == 2:
        return array[0]
    if array.ndim == 1:
        return array
    raise ValueError(f"Unsupported SHAP output shape: {array.shape}")


def _feature_value_text(feature: str, value: Any) -> str:
    if feature == "loan_percent_income":
        return format_percent(float(value))
    if feature in {"person_income", "loan_amnt"}:
        return format_money(float(value))
    if feature == "loan_int_rate":
        return f"{float(value):.2f}%"
    if feature in {"person_emp_length", "cb_person_cred_hist_length"}:
        return f"{float(value):g} years"
    if feature == "person_age":
        return f"{int(value)} years"
    return str(value).replace("_", " ").title()


def shap_applicant_explanations(
    bundle: dict[str, Any],
    application: pd.DataFrame,
) -> list[dict[str, str]]:
    pipeline = bundle["pipeline"]
    preprocessor = pipeline.named_steps["preprocessor"]
    classifier = pipeline.named_steps["classifier"]
    transformed = preprocessor.transform(application)
    transformed_names = preprocessor.get_feature_names_out()
    values = _default_class_shap_values(
        _tree_explainer(classifier).shap_values(transformed)
    )

    contributions = {feature: 0.0 for feature in bundle["features"]}
    for transformed_name, contribution in zip(transformed_names, values):
        source = _source_feature(str(transformed_name), bundle["features"])
        contributions[source] = contributions.get(source, 0.0) + float(contribution)

    applicant = application.iloc[0].to_dict()
    ranked = sorted(
        contributions.items(),
        key=lambda item: abs(item[1]),
        reverse=True,
    )[:5]

    rows = []
    for feature, contribution in ranked:
        raises_risk = contribution > 0
        direction = "toward default" if raises_risk else "toward non-default"
        rows.append(
            {
                "factor": pretty_feature_name(feature),
                "detail": (
                    f"Applicant value: {_feature_value_text(feature, applicant[feature])}. "
                    f"SHAP impact {contribution:+.3f}, moving the model {direction}."
                ),
                "impact": "Raises model risk" if raises_risk else "Lowers model risk",
                "class": "negative" if raises_risk else "positive",
            }
        )
    return rows


def applicant_explanations(
    bundle: dict[str, Any],
    application: pd.DataFrame,
    form: dict[str, Any],
) -> tuple[list[dict[str, str]], str]:
    try:
        rows = shap_applicant_explanations(bundle, application)
        if rows:
            return (
                rows,
                "Tree SHAP ranks the five applicant fields with the largest local impact on this prediction.",
            )
    except Exception as exc:
        LOGGER.exception("Falling back to policy-based applicant explanations: %s", exc)

    return (
        policy_applicant_explanations(form),
        "Model explanation is temporarily unavailable; these fallback indicators use transparent lending-risk rules.",
    )


def policy_applicant_explanations(form: dict[str, Any]) -> list[dict[str, str]]:
    loan_percent_income = float(form["loan_percent_income"])
    loan_grade = str(form["loan_grade"])
    prior_default = str(form["cb_person_default_on_file"])
    income = float(form["person_income"])
    interest_rate = float(form["loan_int_rate"])

    rows = []
    if loan_percent_income < 0.20:
        rows.append(
            {
                "factor": "Loan % of income",
                "detail": f"{format_percent(loan_percent_income)} is low for the requested loan.",
                "impact": "Reduces risk",
                "class": "positive",
            }
        )
    elif loan_percent_income <= 0.35:
        rows.append(
            {
                "factor": "Loan % of income",
                "detail": f"{format_percent(loan_percent_income)} is moderate.",
                "impact": "Neutral to moderate risk",
                "class": "neutral",
            }
        )
    else:
        rows.append(
            {
                "factor": "Loan % of income",
                "detail": f"{format_percent(loan_percent_income)} is high.",
                "impact": "Increases risk",
                "class": "negative",
            }
        )

    if loan_grade in {"A", "B"}:
        rows.append(
            {
                "factor": "Loan grade",
                "detail": f"Grade {loan_grade} is a stronger credit tier in this dataset.",
                "impact": "Reduces risk",
                "class": "positive",
            }
        )
    elif loan_grade in {"C"}:
        rows.append(
            {
                "factor": "Loan grade",
                "detail": f"Grade {loan_grade} is a middle credit tier.",
                "impact": "Moderate risk",
                "class": "neutral",
            }
        )
    else:
        rows.append(
            {
                "factor": "Loan grade",
                "detail": f"Grade {loan_grade} is associated with higher observed default risk.",
                "impact": "Increases risk",
                "class": "negative",
            }
        )

    rows.append(
        {
            "factor": "Prior default",
            "detail": "No prior default is on file." if prior_default == "N" else "A prior default is on file.",
            "impact": "Reduces risk" if prior_default == "N" else "Increases risk",
            "class": "positive" if prior_default == "N" else "negative",
        }
    )

    if income >= 50_000:
        rows.append(
            {
                "factor": "Income",
                "detail": f"{format_money(income)} suggests a more stable repayment profile.",
                "impact": "Reduces risk",
                "class": "positive",
            }
        )
    else:
        rows.append(
            {
                "factor": "Income",
                "detail": f"{format_money(income)} leaves less repayment cushion.",
                "impact": "Increases risk",
                "class": "negative",
            }
        )

    if interest_rate <= 10:
        impact = ("Lower interest rate", "Reduces risk", "positive")
    elif interest_rate <= 15:
        impact = ("Moderate interest rate", "Neutral to moderate risk", "neutral")
    else:
        impact = ("Higher interest rate", "Increases risk", "negative")
    rows.append(
        {
            "factor": "Interest rate",
            "detail": f"{interest_rate:.2f}% is a {impact[0].lower()}.",
            "impact": impact[1],
            "class": impact[2],
        }
    )
    return rows


def report_artifact_path(file_name: str) -> Path | None:
    if file_name not in REPORT_ARTIFACTS:
        return None
    path = REPORTS_DIR / file_name
    return path if path.exists() else None


def report_summary(dashboard: dict[str, Any]) -> dict[str, Any]:
    data = dashboard["data"]
    threshold_table = dashboard["threshold_table"]
    business_threshold = float(dashboard["threshold"])
    threshold_row = nearest_threshold_row(threshold_table, business_threshold)
    default_rate = float(data["loan_status"].mean())
    business_metrics = dashboard["business_metrics"]
    default_metrics = dashboard["default_metrics"]
    metadata = model_metadata(dashboard["bundle"])

    return {
        "model_summary": [
            {"label": "Best model", "value": str(dashboard["best_model"])},
            {"label": "Model version", "value": metadata["version"]},
            {"label": "Trained", "value": metadata["trained_at"]},
            {"label": "F1-score", "value": format_score(float(dashboard["best_f1"]))},
            {"label": "ROC-AUC", "value": format_score(float(default_metrics["roc_auc"]))},
            {"label": "Model type", "value": "Calibrated leakage-safe Pipeline"},
        ],
        "dataset_summary": [
            {"label": "Applicants", "value": f"{len(data):,}"},
            {"label": "Columns", "value": f"{len(data.columns):,}"},
            {"label": "Observed default rate", "value": format_percent(default_rate)},
            {"label": "Target", "value": "loan_status"},
        ],
        "threshold_summary": [
            {"label": "Chosen threshold", "value": f"{business_threshold:.2f}"},
            {"label": "Business recall", "value": format_score(float(business_metrics["recall"]))},
            {"label": "Business F1-score", "value": format_score(float(business_metrics["f1_score"]))},
            {"label": "Business cost", "value": f"{int(threshold_row.get('business_cost', 0)):,}"},
        ],
        "confusion": [
            {
                "actual": "Actual non-default",
                "predicted_non_default": f"{int(threshold_row.get('true_negatives', 0)):,}",
                "predicted_default": f"{int(threshold_row.get('false_positives', 0)):,}",
            },
            {
                "actual": "Actual default",
                "predicted_non_default": f"{int(threshold_row.get('false_negatives', 0)):,}",
                "predicted_default": f"{int(threshold_row.get('true_positives', 0)):,}",
            },
        ],
        "business_recommendation": (
            "Use the recommended threshold only for screening and route flagged applications to "
            "human review. The production scoring path excludes lender-assigned grade and pricing; "
            "review calibration, drift, and subgroup diagnostics before operational use."
        ),
    }


def summary_csv(dashboard: dict[str, Any]) -> str:
    summary = report_summary(dashboard)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["section", "metric", "value"])
    for section in ("model_summary", "dataset_summary", "threshold_summary"):
        for row in summary[section]:
            writer.writerow([section, row["label"], row["value"]])
    writer.writerow(["business_recommendation", "recommendation", summary["business_recommendation"]])
    return buffer.getvalue()


def summary_pdf(dashboard: dict[str, Any]) -> bytes:
    summary = report_summary(dashboard)
    buffer = io.BytesIO()
    with PdfPages(buffer) as pdf:
        figure = Figure(figsize=(8.5, 11))
        axis = figure.subplots()
        axis.axis("off")

        y = 0.96
        axis.text(0.05, y, "BankRisk Compass Report", fontsize=18, fontweight="bold", color="#071942")
        y -= 0.055
        axis.text(0.05, y, f"Generated: {display_date()}", fontsize=10, color="#60708d")
        y -= 0.06

        for title, section in [
            ("Model Summary", "model_summary"),
            ("Dataset Summary", "dataset_summary"),
            ("Threshold Summary", "threshold_summary"),
        ]:
            axis.text(0.05, y, title, fontsize=13, fontweight="bold", color="#062f6c")
            y -= 0.032
            for row in summary[section]:
                axis.text(0.07, y, f"{row['label']}: {row['value']}", fontsize=10, color="#071942")
                y -= 0.026
            y -= 0.018

        axis.text(0.05, y, "Business Recommendation", fontsize=13, fontweight="bold", color="#062f6c")
        y -= 0.034
        axis.text(
            0.07,
            y,
            summary["business_recommendation"],
            fontsize=10,
            color="#071942",
            wrap=True,
        )
        pdf.savefig(figure, bbox_inches="tight")

    buffer.seek(0)
    return buffer.getvalue()


def markdown_to_html(text: str) -> str:
    if not text:
        return "<p>Run training to generate the business report.</p>"

    lines = text.splitlines()
    output: list[str] = []
    paragraph: list[str] = []
    in_list = False
    in_code = False
    code_lines: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            output.append(f"<p>{' '.join(paragraph)}</p>")
            paragraph.clear()

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            output.append("</ul>")
            in_list = False

    index = 0
    while index < len(lines):
        raw_line = lines[index]
        line = raw_line.strip()

        if line.startswith("```"):
            if in_code:
                output.append(f"<pre>{html.escape(chr(10).join(code_lines))}</pre>")
                code_lines.clear()
                in_code = False
            else:
                flush_paragraph()
                close_list()
                in_code = True
            index += 1
            continue

        if in_code:
            code_lines.append(raw_line)
            index += 1
            continue

        if not line:
            flush_paragraph()
            close_list()
            index += 1
            continue

        if line.startswith("|") and index + 1 < len(lines) and lines[index + 1].strip().startswith("|---"):
            flush_paragraph()
            close_list()
            table_lines = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index].strip())
                index += 1

            rows = [
                [html.escape(cell.strip()) for cell in table_line.strip("|").split("|")]
                for table_line in table_lines
            ]
            if len(rows) >= 2:
                output.append("<table>")
                output.append("<thead><tr>")
                output.extend(f"<th>{cell}</th>" for cell in rows[0])
                output.append("</tr></thead><tbody>")
                for row in rows[2:]:
                    output.append("<tr>")
                    output.extend(f"<td>{cell}</td>" for cell in row)
                    output.append("</tr>")
                output.append("</tbody></table>")
            continue

        if line.startswith("## "):
            flush_paragraph()
            close_list()
            output.append(f"<h3>{html.escape(line[3:])}</h3>")
        elif line.startswith("# "):
            flush_paragraph()
            close_list()
            output.append(f"<h2>{html.escape(line[2:])}</h2>")
        elif line.startswith("- "):
            flush_paragraph()
            if not in_list:
                output.append("<ul>")
                in_list = True
            output.append(f"<li>{html.escape(line[2:])}</li>")
        else:
            paragraph.append(html.escape(line))

        index += 1

    flush_paragraph()
    close_list()
    if in_code:
        output.append(f"<pre>{html.escape(chr(10).join(code_lines))}</pre>")

    return "\n".join(output)
