from __future__ import annotations

from django.urls import path

from . import views


urlpatterns = [
    path("", views.overview, name="overview"),
    path("assessment/", views.assessment, name="assessment"),
    path("insights/", views.insights, name="insights"),
    path("threshold/", views.threshold_analysis, name="threshold"),
    path("reports/", views.reports, name="reports"),
    path("reports/download/summary.csv", views.download_summary_csv, name="download-summary-csv"),
    path("reports/download/summary.pdf", views.download_summary_pdf, name="download-summary-pdf"),
    path("report-artifacts/<str:file_name>/", views.report_artifact, name="report-artifact"),
]
