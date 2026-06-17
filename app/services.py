from __future__ import annotations

import html
import io
import csv
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "data" / "credit_risk.csv"
MODEL_PATH = PROJECT_ROOT / "models" / "credit_risk_model.pkl"
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


@lru_cache(maxsize=1)
def load_model_bundle() -> dict[str, Any]:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            "Model file not found. Run `python -m src.train_model --quick` from the project root first."
        )
    return joblib.load(MODEL_PATH)


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
    return float(bundle["pipeline"].predict_proba(application)[:, 1][0])


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


def _float_from_payload(
    payload: Any,
    key: str,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    try:
        value = float(payload.get(key, default))
    except (TypeError, ValueError):
        value = default
    return min(max(value, minimum), maximum)


def _int_from_payload(
    payload: Any,
    key: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    return int(round(_float_from_payload(payload, key, float(default), minimum, maximum)))


def _choice_from_payload(
    payload: Any,
    key: str,
    choices: list[str],
    default: str,
) -> str:
    value = str(payload.get(key, default))
    return value if value in choices else default


def application_from_payload(
    bundle: dict[str, Any],
    payload: Any | None,
) -> tuple[dict[str, Any], pd.DataFrame]:
    reference = bundle["feature_reference"]
    medians = reference["numeric_medians"]
    modes = reference["categorical_modes"]
    options = reference["categorical_options"]
    payload = payload or {}

    values = {
        "person_age": _int_from_payload(payload, "person_age", int(medians["person_age"]), 18, 100),
        "person_income": _int_from_payload(
            payload,
            "person_income",
            int(medians["person_income"]),
            0,
            2_000_000,
        ),
        "person_emp_length": _float_from_payload(
            payload,
            "person_emp_length",
            float(round(medians["person_emp_length"], 1)),
            0.0,
            60.0,
        ),
        "loan_amnt": _int_from_payload(payload, "loan_amnt", int(medians["loan_amnt"]), 500, 500_000),
        "loan_int_rate": _float_from_payload(
            payload,
            "loan_int_rate",
            float(round(medians["loan_int_rate"], 2)),
            0.0,
            40.0,
        ),
        "cb_person_cred_hist_length": _int_from_payload(
            payload,
            "cb_person_cred_hist_length",
            int(medians["cb_person_cred_hist_length"]),
            0,
            50,
        ),
        "person_home_ownership": _choice_from_payload(
            payload,
            "person_home_ownership",
            options["person_home_ownership"],
            modes["person_home_ownership"],
        ),
        "loan_intent": _choice_from_payload(
            payload,
            "loan_intent",
            options["loan_intent"],
            modes["loan_intent"],
        ),
        "loan_grade": _choice_from_payload(
            payload,
            "loan_grade",
            options["loan_grade"],
            modes["loan_grade"],
        ),
        "cb_person_default_on_file": _choice_from_payload(
            payload,
            "cb_person_default_on_file",
            options["cb_person_default_on_file"],
            modes["cb_person_default_on_file"],
        ),
    }
    income = float(values["person_income"])
    loan_percent_income = float(values["loan_amnt"]) / income if income else 1.0
    values["loan_percent_income"] = float(round(loan_percent_income, 4))

    application = pd.DataFrame([values])[bundle["features"]]
    return values, application


def assessment_result(bundle: dict[str, Any], payload: Any | None) -> dict[str, Any]:
    form, application = application_from_payload(bundle, payload)
    probability = predict_default_probability(bundle, application)
    category, category_class, category_color = risk_category(probability, bundle)
    threshold = float(bundle.get("threshold", 0.5))
    prediction = "Likely Default" if probability >= threshold else "Likely Non-default"
    if probability >= threshold:
        decision = "Manual review before approval" if category != "High" else "Manual review or decline"
    else:
        decision = "Approve with monitoring"

    snapshot = []
    row = application.iloc[0].to_dict()
    for feature in bundle["features"]:
        value = row[feature]
        if feature == "loan_percent_income":
            display_value = format_percent(float(value))
        elif feature in {"person_income", "loan_amnt"}:
            display_value = format_money(float(value))
        elif isinstance(value, float):
            display_value = f"{value:.2f}"
        else:
            display_value = str(value)
        snapshot.append({"feature": pretty_feature_name(feature), "value": display_value})

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
        "explanation_rows": applicant_explanations(form),
    }


def applicant_explanations(form: dict[str, Any]) -> list[dict[str, str]]:
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


def form_options(bundle: dict[str, Any]) -> dict[str, list[str]]:
    return bundle["feature_reference"]["categorical_options"]


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

    return {
        "model_summary": [
            {"label": "Best model", "value": str(dashboard["best_model"])},
            {"label": "F1-score", "value": format_score(float(dashboard["best_f1"]))},
            {"label": "ROC-AUC", "value": format_score(float(default_metrics["roc_auc"]))},
            {"label": "Model type", "value": "Leakage-safe scikit-learn Pipeline"},
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
            "Use the recommended business threshold for screening, send borderline or high-risk "
            "applications to manual review, and test a second model without lender-assigned fields "
            "such as loan grade and interest rate."
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
