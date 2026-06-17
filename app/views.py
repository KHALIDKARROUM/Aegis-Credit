from __future__ import annotations

import mimetypes

from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import render

from . import services


PAGES = [
    {"number": "01", "key": "overview", "label": "Overview", "url_name": "overview"},
    {"number": "02", "key": "assessment", "label": "Loan Assessment", "url_name": "assessment"},
    {"number": "03", "key": "insights", "label": "Model Insights", "url_name": "insights"},
    {"number": "04", "key": "threshold", "label": "Threshold Analysis", "url_name": "threshold"},
    {"number": "05", "key": "reports", "label": "Reports", "url_name": "reports"},
]


def base_context(active_page: str) -> tuple[dict[str, object], dict[str, object] | None]:
    context: dict[str, object] = {
        "pages": PAGES,
        "active_page": active_page,
        "best_model": "Unavailable",
        "display_date": services.display_date(),
    }

    try:
        dashboard = services.dashboard_data()
    except FileNotFoundError as exc:
        context["error_message"] = str(exc)
        return context, None

    context["best_model"] = dashboard["best_model"]
    return context, dashboard


def overview(request: HttpRequest) -> HttpResponse:
    context, dashboard = base_context("overview")
    if dashboard is None:
        return render(request, "app/overview.html", context)

    data = dashboard["data"]
    comparison = dashboard["comparison"]
    importance = dashboard["importance"]
    default_metrics = dashboard["default_metrics"]
    business_metrics = dashboard["business_metrics"]
    threshold = float(dashboard["threshold"])
    default_rate = float(data["loan_status"].mean())

    context.update(
        {
            "metric_tiles": [
                {
                    "label": "Applicants",
                    "value": f"{len(data):,}",
                    "foot": "Rows in data/credit_risk.csv",
                },
                {
                    "label": "Observed Default Rate",
                    "value": services.format_percent(default_rate),
                    "foot": "Target class share",
                },
                {
                    "label": "Best Model",
                    "value": str(dashboard["best_model"]),
                    "foot": f"F1-score {services.format_score(float(dashboard['best_f1']))}",
                },
                {
                    "label": "Business Threshold",
                    "value": f"{threshold:.2f}",
                    "foot": f"Recall {services.format_score(float(business_metrics['recall']))}",
                },
            ],
            "grade_bars": services.default_rate_by_grade(data),
            "intent_bars": services.default_rate_by_intent(data),
            "default_metrics_pairs": services.metric_pairs(
                default_metrics,
                [
                    ("accuracy", "Accuracy", "percent"),
                    ("f1_score", "F1-score", "score"),
                    ("recall", "Recall for defaults", "score"),
                    ("roc_auc", "ROC-AUC", "score"),
                ],
            ),
            "business_metrics_pairs": services.metric_pairs(
                business_metrics,
                [
                    ("accuracy", "Accuracy", "percent"),
                    ("f1_score", "F1-score", "score"),
                    ("recall", "Recall for defaults", "score"),
                ],
            ),
            "business_threshold": f"{float(business_metrics['decision_threshold']):.2f}",
            "model_comparison_table": services.dataframe_table(comparison, digits=3),
            "model_comparison_bars": services.model_comparison_bars(comparison),
            "top_feature": (
                services.pretty_feature_name(str(importance.iloc[0]["feature"]))
                if not importance.empty
                else "Interest Rate"
            ),
            "portfolio_default_rate": services.format_percent(default_rate),
        }
    )
    return render(request, "app/overview.html", context)


def assessment(request: HttpRequest) -> HttpResponse:
    context, dashboard = base_context("assessment")
    if dashboard is None:
        return render(request, "app/assessment.html", context)

    bundle = dashboard["bundle"]
    payload = request.POST if request.method == "POST" else None
    context.update(services.assessment_result(bundle, payload))
    context["options"] = services.form_options(bundle)
    return render(request, "app/assessment.html", context)


def insights(request: HttpRequest) -> HttpResponse:
    context, dashboard = base_context("insights")
    if dashboard is None:
        return render(request, "app/insights.html", context)

    context.update(
        {
            "model_comparison_table": services.dataframe_table(
                dashboard["comparison"],
                digits=3,
            ),
            "model_comparison_bars": services.model_comparison_bars(dashboard["comparison"]),
            "importance_bars": services.importance_bars(dashboard["importance"]),
        }
    )
    return render(request, "app/insights.html", context)


def threshold_analysis(request: HttpRequest) -> HttpResponse:
    context, dashboard = base_context("threshold")
    if dashboard is None:
        return render(request, "app/threshold.html", context)

    threshold_table = dashboard["threshold_table"]
    default_threshold = float(dashboard["threshold"])
    try:
        selected_threshold = float(request.GET.get("threshold", default_threshold))
    except (TypeError, ValueError):
        selected_threshold = default_threshold
    selected_threshold = min(max(selected_threshold, 0.10), 0.90)
    threshold_context = services.threshold_summary_context(
        threshold_table,
        selected_threshold,
        default_threshold,
    )
    row = threshold_context["row"]

    context.update(
        {
            "selected_threshold": threshold_context["selected_threshold"],
            "business_threshold": threshold_context["business_threshold"],
            "current_threshold_label": threshold_context["current_threshold_label"],
            "business_threshold_label": threshold_context["business_threshold_label"],
            "threshold_summary": [
                {
                    "label": "Current Selected Threshold",
                    "value": f"{float(row.get('threshold', selected_threshold)):.2f}",
                    "foot": "Interactive scenario shown below",
                },
                {
                    "label": "Recommended Business Threshold",
                    "value": f"{default_threshold:.2f}",
                    "foot": "Chosen by 5:1 FN to FP cost",
                },
                {
                    "label": "False Positives",
                    "value": f"{int(row.get('false_positives', 0)):,}",
                    "foot": "Safer applicants routed to review",
                },
                {
                    "label": "False Negatives",
                    "value": f"{int(row.get('false_negatives', 0)):,}",
                    "foot": "Defaults missed by policy",
                },
                {
                    "label": "Business Cost",
                    "value": f"{int(row.get('business_cost', 0)):,}",
                    "foot": "5x FN + 1x FP",
                },
            ],
            "confusion": [
                {
                    "actual": "Actual non-default",
                    "predicted_non_default": f"{int(row.get('true_negatives', 0)):,}",
                    "predicted_default": f"{int(row.get('false_positives', 0)):,}",
                },
                {
                    "actual": "Actual default",
                    "predicted_non_default": f"{int(row.get('false_negatives', 0)):,}",
                    "predicted_default": f"{int(row.get('true_positives', 0)):,}",
                },
            ],
            "threshold_table": services.dataframe_table(threshold_table, digits=3),
        }
    )
    return render(request, "app/threshold.html", context)


def reports(request: HttpRequest) -> HttpResponse:
    context, dashboard = base_context("reports")
    if dashboard is None:
        return render(request, "app/reports.html", context)

    summary = services.report_summary(dashboard)
    context.update(
        {
            "report_summary": summary,
            "business_report_html": services.markdown_to_html(
                services.load_text_report("business_report.md")
            ),
            "classification_report": services.load_text_report("classification_report.txt")
            or "Run training to generate classification report.",
            "final_metrics_table": services.dataframe_table(
                dashboard["final_metrics"],
                digits=3,
            ),
            "artifact_rows": [
                {"artifact": "business_report.md", "purpose": "Final written interpretation"},
                {"artifact": "model_comparison.csv", "purpose": "Model comparison metrics"},
                {"artifact": "final_model_metrics.csv", "purpose": "Default and business threshold metrics"},
                {"artifact": "threshold_analysis.csv", "purpose": "Precision/recall/cost by threshold"},
                {"artifact": "permutation_importance.csv", "purpose": "Global model drivers"},
                {"artifact": "credit_risk_model.pkl", "purpose": "Saved model bundle"},
            ],
        }
    )
    return render(request, "app/reports.html", context)


def download_summary_csv(request: HttpRequest) -> HttpResponse:
    _, dashboard = base_context("reports")
    if dashboard is None:
        raise Http404("Report summary is unavailable.")

    response = HttpResponse(services.summary_csv(dashboard), content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="bankrisk_summary.csv"'
    return response


def download_summary_pdf(request: HttpRequest) -> HttpResponse:
    _, dashboard = base_context("reports")
    if dashboard is None:
        raise Http404("Report summary is unavailable.")

    response = HttpResponse(services.summary_pdf(dashboard), content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="bankrisk_summary.pdf"'
    return response


def report_artifact(request: HttpRequest, file_name: str) -> FileResponse:
    path = services.report_artifact_path(file_name)
    if path is None:
        raise Http404("Report artifact not found.")

    content_type, _ = mimetypes.guess_type(str(path))
    return FileResponse(path.open("rb"), content_type=content_type or "application/octet-stream")
