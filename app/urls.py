from __future__ import annotations

from django.urls import path

from . import views


urlpatterns = [
    path("healthz/", views.health, name="health"),
    path("readyz/", views.readiness, name="readiness"),
    path("api/v1/score/", views.score_api, name="score-api"),
    path("api/v1/openapi.json", views.openapi_json, name="openapi-json"),
    path("api/docs/", views.api_docs, name="api-docs"),
    path("", views.assessment, name="assessment"),
    path("assessment/", views.assessment, name="assessment-legacy"),
    path("overview/", views.overview, name="overview"),
    path("cases/", views.case_list, name="case-list"),
    path("cases/<uuid:case_id>/", views.case_detail, name="case-detail"),
    path("batch/", views.batch_upload, name="batch-upload"),
    path("batch/template.csv", views.batch_template, name="batch-template"),
    path("batch/<uuid:batch_id>/", views.batch_detail, name="batch-detail"),
    path("batch/<uuid:batch_id>/cancel/", views.batch_cancel, name="batch-cancel"),
    path("batch/<uuid:batch_id>/retry/", views.batch_retry, name="batch-retry"),
    path("batch/<uuid:batch_id>/results.csv", views.batch_results, name="batch-results"),
    path("monitoring/", views.monitoring, name="monitoring"),
    path(
        "monitoring/<uuid:run_id>/acknowledge/",
        views.monitoring_acknowledge,
        name="monitoring-acknowledge",
    ),
    path("business-policy/", views.business_policy, name="business-policy"),
    path(
        "business-policy/scenarios/<uuid:scenario_id>/decision/",
        views.policy_scenario_decision,
        name="policy-scenario-decision",
    ),
    path("insights/", views.insights, name="insights"),
    path("threshold/", views.threshold_analysis, name="threshold"),
    path("reports/", views.reports, name="reports"),
    path("reports/download/summary.csv", views.download_summary_csv, name="download-summary-csv"),
    path("reports/download/summary.pdf", views.download_summary_pdf, name="download-summary-pdf"),
    path("report-artifacts/<str:file_name>/", views.report_artifact, name="report-artifact"),
]
