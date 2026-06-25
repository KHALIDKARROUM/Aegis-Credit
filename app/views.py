from __future__ import annotations

import mimetypes
import logging
import json

from django.conf import settings
from django.utils.crypto import constant_time_compare
from django.db import DatabaseError
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import services
from .forms import ApplicantAssessmentForm
from .models import PredictionAudit


LOGGER = logging.getLogger(__name__)
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
        "model_meta": {"version": "unavailable", "trained_at": "unavailable"},
        "display_date": services.display_date(),
    }

    try:
        dashboard = services.dashboard_data()
    except (FileNotFoundError, services.ArtifactIntegrityError) as exc:
        context["error_message"] = str(exc)
        return context, None

    context["best_model"] = dashboard["best_model"]
    context["model_meta"] = services.model_metadata(dashboard["bundle"])
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
    form = ApplicantAssessmentForm(
        request.POST or None,
        bundle=bundle,
    )
    context.update(
        {
            "assessment_form": form,
            "has_result": False,
            "threshold": float(bundle.get("threshold", 0.5)),
            "distribution_warnings": [],
        }
    )

    if request.method == "POST" and form.is_valid():
        result = services.assessment_result(bundle, form.cleaned_data)
        context.update(result)
        context["has_result"] = True
        context["distribution_warnings"] = form.distribution_warnings()
        _write_prediction_audit(result, bundle)

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
            "calibration_table": services.dataframe_table(
                dashboard["calibration"],
                digits=3,
            ),
            "fairness_table": services.dataframe_table(
                dashboard["fairness"],
                digits=3,
            ),
            "artifact_rows": [
                {"artifact": "business_report.md", "purpose": "Final written interpretation"},
                {"artifact": "model_comparison.csv", "purpose": "Model comparison metrics"},
                {"artifact": "final_model_metrics.csv", "purpose": "Default and business threshold metrics"},
                {"artifact": "threshold_analysis.csv", "purpose": "Precision/recall/cost by threshold"},
                {"artifact": "permutation_importance.csv", "purpose": "Global model drivers"},
                {"artifact": "calibration_analysis.csv", "purpose": "Probability calibration diagnostics"},
                {"artifact": "fairness_age_groups.csv", "purpose": "Age-group monitoring diagnostics"},
                {"artifact": "metric_confidence_intervals.csv", "purpose": "Bootstrap uncertainty intervals"},
                {"artifact": "drift_monitoring.csv", "purpose": "Latest feature-distribution drift check"},
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


@never_cache
def health(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


@never_cache
def readiness(request: HttpRequest) -> JsonResponse:
    try:
        bundle = services.load_model_bundle()
        services.load_credit_data()
    except Exception as exc:
        LOGGER.exception("Readiness check failed: %s", exc)
        return JsonResponse({"status": "not-ready"}, status=503)

    return JsonResponse(
        {
            "status": "ready",
            "model_version": str(bundle.get("model_version", "legacy")),
        }
    )


def _write_prediction_audit(result: dict[str, object], bundle: dict[str, object]) -> None:
    try:
        PredictionAudit.objects.create(
            feature_digest=services.feature_digest(result["application"]),
            probability=result["probability"],
            threshold=result["threshold"],
            risk_category=result["category"],
            decision=result["decision"],
            model_version=str(bundle.get("model_version", "legacy")),
        )
    except DatabaseError:
        LOGGER.exception("Prediction audit could not be stored.")


@csrf_exempt
@require_POST
def score_api(request: HttpRequest) -> JsonResponse:
    configured_key = settings.SCORING_API_KEY
    if not configured_key:
        return JsonResponse({"error": "Scoring API is not configured."}, status=503)

    supplied_key = request.headers.get("X-API-Key", "")
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        supplied_key = authorization.removeprefix("Bearer ").strip()
    if not constant_time_compare(supplied_key, configured_key):
        return JsonResponse({"error": "Unauthorized."}, status=401)

    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Request body must be valid JSON."}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "Request body must be a JSON object."}, status=400)

    try:
        bundle = services.load_model_bundle()
    except Exception:
        LOGGER.exception("Scoring API model load failed.")
        return JsonResponse({"error": "Model is unavailable."}, status=503)

    form = ApplicantAssessmentForm(payload, bundle=bundle)
    if not form.is_valid():
        return JsonResponse(
            {
                "error": "Validation failed.",
                "fields": form.errors.get_json_data(),
            },
            status=400,
        )

    result = services.assessment_result(bundle, form.cleaned_data, explain=False)
    _write_prediction_audit(result, bundle)
    return JsonResponse(
        {
            "model_version": str(bundle.get("model_version", "legacy")),
            "probability": round(float(result["probability"]), 6),
            "risk_category": result["category"],
            "screening_result": result["prediction"],
            "recommended_next_step": result["decision"],
            "threshold": result["threshold"],
            "warnings": form.distribution_warnings(),
        }
    )
