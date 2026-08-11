from __future__ import annotations

import json
import logging
import mimetypes
import uuid

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.db.models.functions import TruncDate
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import services
from .access import access_required, record_sensitive_access, user_role
from .forms import (
    ApplicantAssessmentForm,
    BatchUploadForm,
    BusinessEconomicsForm,
    CaseReviewForm,
)
from .models import AssessmentCase, BatchAssessment, PredictionAudit


LOGGER = logging.getLogger(__name__)
PAGES = [
    {"key": "assessment", "label": "New assessment", "url_name": "overview"},
    {"key": "cases", "label": "Cases", "url_name": "case-list"},
    {"key": "batch", "label": "Batch load", "url_name": "batch-upload"},
    {"key": "monitoring", "label": "Monitoring", "url_name": "monitoring"},
    {"key": "business", "label": "Business policy", "url_name": "business-policy"},
    {"key": "reports", "label": "Reports", "url_name": "reports"},
    {"key": "api", "label": "API", "url_name": "api-docs"},
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


def assessment_context() -> tuple[dict[str, object], dict[str, object] | None]:
    context: dict[str, object] = {
        "pages": PAGES,
        "active_page": "assessment",
        "display_date": services.display_date(),
    }
    try:
        bundle = services.load_model_bundle()
    except (FileNotFoundError, services.ArtifactIntegrityError) as exc:
        # A disabled model is an expected, safe state for a local checkout that
        # contains demonstration data rather than an approved model release.
        LOGGER.warning("Assessment service is unavailable: %s", exc)
        if isinstance(exc, services.ArtifactIntegrityError) and not settings.DATA_PROVENANCE_VERIFIED:
            context.update(
                {
                    "error_title": "Scoring is disabled for this demonstration project",
                    "error_message": (
                        "The bundled dataset and model have not been approved for operational use, "
                        "so BankRisk Compass will not produce loan-risk scores."
                    ),
                    "error_guidance": (
                        "This is expected in a local checkout. Scoring can only be enabled with an "
                        "approved, signed model release and verified data provenance."
                    ),
                }
            )
        else:
            context.update(
                {
                    "error_title": "Assessment service unavailable",
                    "error_message": "The approved model release could not be loaded.",
                    "error_guidance": "Check the model release configuration and try again.",
                }
            )
        return context, None
    return context, bundle


def _actor(request: HttpRequest):
    return request.user if request.user.is_authenticated else None


def _case_payload(case: AssessmentCase) -> dict[str, object]:
    return {
        "case_id": str(case.id),
        "model_version": case.model_version,
        "probability": round(case.probability, 6),
        "risk_category": case.risk_category,
        "screening_result": case.screening_result,
        "recommended_next_step": case.recommendation,
        "threshold": case.threshold,
        "warnings": case.warnings,
    }


@transaction.atomic
def _persist_result(
    request: HttpRequest,
    result: dict[str, object],
    bundle: dict[str, object],
    warnings: list[str],
    *,
    source: str,
) -> AssessmentCase:
    request_id = result["request_id"]
    if not isinstance(request_id, uuid.UUID):
        request_id = uuid.UUID(str(request_id))

    case, _ = AssessmentCase.objects.get_or_create(
        request_id=request_id,
        defaults={
            "created_by": _actor(request),
            "source": source,
            "applicant_reference": result.get("applicant_reference", ""),
            "application_data": services.json_safe_application(result),
            "probability": result["probability"],
            "threshold": result["threshold"],
            "risk_category": result["category"],
            "screening_result": result["prediction"],
            "recommendation": result["decision"],
            "model_version": str(bundle.get("model_version", "legacy")),
            "explanation_rows": result["explanation_rows"],
            "explanation_method": result["explanation_method"],
            "warnings": warnings,
        },
    )
    PredictionAudit.objects.get_or_create(
        request_id=request_id,
        defaults={
            "actor": _actor(request),
            "source": source,
            "feature_digest": services.feature_digest(result["application"]),
            "digest_version": "hmac-sha256-v1",
            "probability": result["probability"],
            "threshold": result["threshold"],
            "risk_category": result["category"],
            "decision": result["decision"],
            "model_version": str(bundle.get("model_version", "legacy")),
        },
    )
    record_sensitive_access(request, "case_created", case)
    return case


@access_required("reviewer")
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


@access_required("analyst")
def assessment(request: HttpRequest) -> HttpResponse:
    context, bundle = assessment_context()
    if bundle is None:
        return render(request, "app/assessment.html", context)

    form = ApplicantAssessmentForm(
        request.POST or None,
        bundle=bundle,
        use_demo=request.method == "GET" and request.GET.get("demo") == "1",
    )
    context.update(
        {
            "assessment_form": form,
            "has_result": False,
            "distribution_warnings": [],
        }
    )

    if request.method == "POST" and form.is_valid():
        result = services.assessment_result(bundle, form.cleaned_data)
        context.update(result)
        context["has_result"] = True
        warnings = form.distribution_warnings()
        context["distribution_warnings"] = warnings
        context["saved_case"] = _persist_result(
            request,
            result,
            bundle,
            warnings,
            source="web",
        )

    return render(request, "app/assessment.html", context)


@access_required("reviewer")
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


@access_required("reviewer")
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


@access_required("reviewer")
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


@access_required("reviewer")
def download_summary_csv(request: HttpRequest) -> HttpResponse:
    _, dashboard = base_context("reports")
    if dashboard is None:
        raise Http404("Report summary is unavailable.")

    response = HttpResponse(services.summary_csv(dashboard), content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="bankrisk_summary.csv"'
    return response


@access_required("reviewer")
def download_summary_pdf(request: HttpRequest) -> HttpResponse:
    _, dashboard = base_context("reports")
    if dashboard is None:
        raise Http404("Report summary is unavailable.")

    response = HttpResponse(services.summary_pdf(dashboard), content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="bankrisk_summary.pdf"'
    return response


@access_required("reviewer")
def report_artifact(request: HttpRequest, file_name: str) -> FileResponse:
    path = services.report_artifact_path(file_name)
    if path is None:
        raise Http404("Report artifact not found.")

    content_type, _ = mimetypes.guess_type(str(path))
    return FileResponse(path.open("rb"), content_type=content_type or "application/octet-stream")


@access_required("analyst")
def case_list(request: HttpRequest) -> HttpResponse:
    cases = AssessmentCase.objects.select_related("created_by", "assigned_to")
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    risk = request.GET.get("risk", "").strip()
    if query:
        identifier_filter = Q()
        try:
            identifier_filter = Q(id=uuid.UUID(query))
        except ValueError:
            pass
        cases = cases.filter(Q(applicant_reference__icontains=query) | identifier_filter)
    if status:
        cases = cases.filter(status=status)
    if risk:
        cases = cases.filter(risk_category__iexact=risk)
    displayed_cases = list(cases[:250])
    for case in displayed_cases:
        record_sensitive_access(request, "case_listed", case)
    context = {
        "pages": PAGES,
        "active_page": "cases",
        "display_date": services.display_date(),
        "cases": displayed_cases,
        "query": query,
        "selected_status": status,
        "selected_risk": risk,
        "status_choices": AssessmentCase.Status.choices,
        "risk_choices": ["Low", "Medium", "High"],
    }
    return render(request, "app/case_list.html", context)


@access_required("analyst")
def case_detail(request: HttpRequest, case_id: uuid.UUID) -> HttpResponse:
    case = get_object_or_404(
        AssessmentCase.objects.select_related("created_by", "assigned_to"),
        id=case_id,
    )
    record_sensitive_access(request, "case_viewed", case)
    can_review = user_role(request.user) in {"reviewer", "admin", "local"}
    form = CaseReviewForm(request.POST or None, instance=case)
    if request.method == "POST":
        if not can_review:
            return HttpResponse("Reviewer access is required.", status=403)
        if form.is_valid():
            updated = form.save(commit=False)
            updated.reviewed_at = timezone.now()
            if request.user.is_authenticated and updated.assigned_to_id is None:
                updated.assigned_to = request.user
            updated.save()
            record_sensitive_access(request, "case_reviewed", updated)
            messages.success(request, "Review saved.")
            return redirect("case-detail", case_id=case.id)

    application_rows = [
        {
            "feature": services.pretty_feature_name(feature),
            "value": (
                services.format_money(float(value))
                if feature in {"person_income", "loan_amnt"}
                else services.format_percent(float(value))
                if feature == "loan_percent_income"
                else str(value)
            ),
        }
        for feature, value in case.application_data.items()
    ]
    context = {
        "pages": PAGES,
        "active_page": "cases",
        "display_date": services.display_date(),
        "case": case,
        "review_form": form,
        "can_review": can_review,
        "application_rows": application_rows,
    }
    return render(request, "app/case_detail.html", context)


@access_required("analyst")
def batch_upload(request: HttpRequest) -> HttpResponse:
    context, bundle = assessment_context()
    context["active_page"] = "batch"
    if bundle is None:
        return render(request, "app/batch_upload.html", context)

    form = BatchUploadForm(request.POST or None, request.FILES or None)
    context["batch_form"] = form
    recent_batches = list(BatchAssessment.objects.all()[:20])
    for recent_batch in recent_batches:
        record_sensitive_access(request, "batch_listed", recent_batch)
    context["recent_batches"] = recent_batches
    if request.method == "POST" and form.is_valid():
        upload = form.cleaned_data["file"]
        batch = BatchAssessment.objects.create(
            created_by=_actor(request),
            file_name=upload.name,
        )
        record_sensitive_access(request, "batch_created", batch)
        try:
            frame = services.read_batch_upload(upload)
            results: list[dict[str, object]] = []
            valid_rows = 0
            for index, raw_row in frame.iterrows():
                payload = {
                    key: ("" if __import__("pandas").isna(value) else value)
                    for key, value in raw_row.to_dict().items()
                }
                payload["request_id"] = uuid.uuid4()
                applicant_form = ApplicantAssessmentForm(payload, bundle=bundle)
                if not applicant_form.is_valid():
                    errors = [
                        f"{field}: {message}"
                        for field, messages_for_field in applicant_form.errors.items()
                        for message in messages_for_field
                    ]
                    results.append(
                        {
                            "row": int(index) + 2,
                            "applicant_reference": payload.get("applicant_reference", ""),
                            "status": "invalid",
                            "errors": errors,
                            "warnings": [],
                        }
                    )
                    continue

                result = services.assessment_result(
                    bundle,
                    applicant_form.cleaned_data,
                    explain=False,
                )
                warnings = applicant_form.distribution_warnings()
                case = _persist_result(
                    request,
                    result,
                    bundle,
                    warnings,
                    source="batch",
                )
                valid_rows += 1
                results.append(
                    {
                        "row": int(index) + 2,
                        "applicant_reference": case.applicant_reference,
                        "status": "scored",
                        "case_id": str(case.id),
                        "probability": round(case.probability, 6),
                        "risk_category": case.risk_category,
                        "recommended_next_step": case.recommendation,
                        "warnings": warnings,
                        "errors": [],
                    }
                )
            batch.total_rows = len(frame)
            batch.valid_rows = valid_rows
            batch.invalid_rows = len(frame) - valid_rows
            batch.results = results
            batch.status = BatchAssessment.Status.COMPLETE
            batch.save()
            messages.success(
                request,
                f"Processed {len(frame):,} rows: {valid_rows:,} scored and "
                f"{len(frame) - valid_rows:,} invalid.",
            )
            return redirect("batch-detail", batch_id=batch.id)
        except (ValueError, KeyError, OSError) as exc:
            batch.status = BatchAssessment.Status.FAILED
            batch.results = [{"errors": [str(exc)]}]
            batch.save(update_fields=["status", "results"])
            form.add_error("file", str(exc))

    return render(request, "app/batch_upload.html", context)


@access_required("analyst")
def batch_detail(request: HttpRequest, batch_id: uuid.UUID) -> HttpResponse:
    batch = get_object_or_404(BatchAssessment, id=batch_id)
    record_sensitive_access(request, "batch_viewed", batch)
    return render(
        request,
        "app/batch_detail.html",
        {
            "pages": PAGES,
            "active_page": "batch",
            "display_date": services.display_date(),
            "batch": batch,
        },
    )


@access_required("analyst")
def batch_template(request: HttpRequest) -> HttpResponse:
    response = HttpResponse(services.batch_template_csv(), content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="bankrisk_batch_template.csv"'
    return response


@access_required("analyst")
def batch_results(request: HttpRequest, batch_id: uuid.UUID) -> HttpResponse:
    batch = get_object_or_404(BatchAssessment, id=batch_id)
    record_sensitive_access(request, "batch_results_exported", batch)
    response = HttpResponse(
        services.batch_results_csv(batch.results),
        content_type="text/csv",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="bankrisk_batch_{batch.id}_results.csv"'
    )
    return response


@access_required("reviewer")
def monitoring(request: HttpRequest) -> HttpResponse:
    audits = PredictionAudit.objects.all()
    cases = AssessmentCase.objects.all()
    daily = list(
        audits.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(
            scores=Count("id"),
            average_probability=Avg("probability"),
        )
        .order_by("-day")[:30]
    )
    by_risk = list(
        audits.values("risk_category")
        .annotate(count=Count("id"), average_probability=Avg("probability"))
        .order_by("-count")
    )
    by_source = list(audits.values("source").annotate(count=Count("id")).order_by("-count"))
    reviewed = cases.exclude(reviewed_at=None).count()
    overridden = cases.exclude(override_decision="").count()
    drift = services.load_report_csv("drift_monitoring.csv")
    context = {
        "pages": PAGES,
        "active_page": "monitoring",
        "display_date": services.display_date(),
        "total_scores": audits.count(),
        "open_cases": cases.exclude(status=AssessmentCase.Status.CLOSED).count(),
        "reviewed_cases": reviewed,
        "override_rate": f"{(overridden / reviewed if reviewed else 0):.1%}",
        "daily": daily,
        "by_risk": by_risk,
        "by_source": by_source,
        "drift_table": services.dataframe_table(drift, digits=4),
    }
    return render(request, "app/monitoring.html", context)


@access_required("reviewer")
def business_policy(request: HttpRequest) -> HttpResponse:
    context, dashboard = base_context("business")
    if dashboard is None:
        return render(request, "app/business_policy.html", context)
    form = BusinessEconomicsForm(
        request.GET
        or {
            "average_exposure": "10000",
            "loss_given_default": "0.60",
            "annual_margin": "0.08",
            "review_cost": "35",
        }
    )
    if form.is_valid():
        economics = services.business_economics(
            dashboard["threshold_table"],
            average_exposure=float(form.cleaned_data["average_exposure"]),
            loss_given_default=float(form.cleaned_data["loss_given_default"]),
            annual_margin=float(form.cleaned_data["annual_margin"]),
            review_cost=float(form.cleaned_data["review_cost"]),
        )
    else:
        economics = {"table": dashboard["threshold_table"], "recommended": {}}
    recommended = economics.get("recommended", {})
    recommended_display = (
        {
            "threshold": f"{float(recommended['threshold']):.2f}",
            "estimated_total_cost": f"${float(recommended['estimated_total_cost']):,.0f}",
            "review_rate": services.format_percent(float(recommended["review_rate"])),
            "recall": services.format_score(float(recommended["recall"])),
        }
        if recommended
        else {}
    )
    display_columns = [
        "threshold",
        "precision",
        "recall",
        "review_rate",
        "missed_default_loss",
        "manual_review_cost",
        "false_positive_opportunity_cost",
        "estimated_total_cost",
    ]
    table = economics.get("table")
    if table is not None and not table.empty and "estimated_total_cost" in table:
        table = table[display_columns]
    context.update(
        {
            "economics_form": form,
            "recommended": recommended,
            "recommended_display": recommended_display,
            "economics_table": services.dataframe_table(table, digits=2, max_rows=81),
            "model_threshold": dashboard["threshold"],
        }
    )
    return render(request, "app/business_policy.html", context)


@require_GET
def api_docs(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "app/api_docs.html",
        {
            "pages": PAGES,
            "active_page": "api",
            "display_date": services.display_date(),
            "api_enabled": bool(settings.SCORING_API_KEY),
        },
    )


@require_GET
def openapi_json(request: HttpRequest) -> JsonResponse:
    return JsonResponse(services.openapi_schema())


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
    identifier = f"{supplied_key}:{request.META.get('REMOTE_ADDR', '')}"
    if services.api_rate_limit_exceeded(identifier):
        response = JsonResponse(
            {"error": "Rate limit exceeded. Try again in one minute."},
            status=429,
        )
        response["Retry-After"] = "60"
        return response

    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Request body must be valid JSON."}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "Request body must be a JSON object."}, status=400)

    request_id_value = request.headers.get("Idempotency-Key")
    if request_id_value:
        try:
            request_id = uuid.UUID(request_id_value)
        except ValueError:
            return JsonResponse(
                {"error": "Idempotency-Key must be a valid UUID."},
                status=400,
            )
        existing = AssessmentCase.objects.filter(request_id=request_id).first()
        if existing is not None:
            response = JsonResponse(_case_payload(existing))
            response["Idempotent-Replay"] = "true"
            return response
    else:
        request_id = uuid.uuid4()

    try:
        bundle = services.load_model_bundle()
    except Exception:
        LOGGER.exception("Scoring API model load failed.")
        return JsonResponse({"error": "Model is unavailable."}, status=503)

    payload["request_id"] = request_id
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
    case = _persist_result(
        request,
        result,
        bundle,
        form.distribution_warnings(),
        source="api",
    )
    return JsonResponse(_case_payload(case))
