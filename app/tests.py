from __future__ import annotations

import json
from unittest.mock import patch

import numpy as np
import pandas as pd
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from app import services
from app.forms import ApplicantAssessmentForm
from app.models import PredictionAudit
from src.train_model import (
    EXCLUDED_LENDER_ASSIGNED_FEATURES,
    FEATURES,
    build_threshold_table,
    choose_business_threshold,
    evaluate_predictions,
    load_credit_data,
)


class ApplicantAssessmentFormTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.bundle = services.load_model_bundle()

    def valid_payload(self) -> dict[str, str]:
        return {
            "person_age": "30",
            "person_income": "65000",
            "person_emp_length": "5",
            "person_home_ownership": "RENT",
            "loan_amnt": "8000",
            "loan_intent": "PERSONAL",
            "cb_person_cred_hist_length": "6",
            "cb_person_default_on_file": "N",
        }

    def test_form_uses_only_application_time_features(self) -> None:
        form = ApplicantAssessmentForm(bundle=self.bundle)
        self.assertNotIn("loan_grade", form.fields)
        self.assertNotIn("loan_int_rate", form.fields)
        self.assertEqual(EXCLUDED_LENDER_ASSIGNED_FEATURES, ["loan_int_rate", "loan_grade"])

    def test_valid_application(self) -> None:
        form = ApplicantAssessmentForm(self.valid_payload(), bundle=self.bundle)
        self.assertTrue(form.is_valid(), form.errors)

    def test_zero_income_is_rejected(self) -> None:
        payload = self.valid_payload()
        payload["person_income"] = "0"
        form = ApplicantAssessmentForm(payload, bundle=self.bundle)
        self.assertFalse(form.is_valid())
        self.assertIn("person_income", form.errors)

    def test_impossible_employment_history_is_rejected(self) -> None:
        payload = self.valid_payload()
        payload.update({"person_age": "20", "person_emp_length": "10"})
        form = ApplicantAssessmentForm(payload, bundle=self.bundle)
        self.assertFalse(form.is_valid())
        self.assertIn("person_emp_length", form.errors)

    def test_extreme_but_valid_values_generate_warning(self) -> None:
        payload = self.valid_payload()
        payload.update(
            {
                "person_age": "90",
                "person_income": "10000",
                "loan_amnt": "10000",
                "person_emp_length": "1",
                "cb_person_cred_hist_length": "1",
            }
        )
        form = ApplicantAssessmentForm(payload, bundle=self.bundle)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.distribution_warnings())


class ServiceTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.bundle = services.load_model_bundle()

    def test_bundle_has_governance_metadata(self) -> None:
        for key in (
            "model_version",
            "trained_at_utc",
            "data_sha256",
            "git_commit",
            "split_sizes",
            "runtime_versions",
            "predictor",
        ):
            self.assertIn(key, self.bundle)

    def test_application_frame_matches_model_contract(self) -> None:
        cleaned = {
            "person_age": 30,
            "person_income": 65000,
            "person_emp_length": 5.0,
            "person_home_ownership": "RENT",
            "loan_amnt": 8000,
            "loan_intent": "PERSONAL",
            "cb_person_cred_hist_length": 6,
            "cb_person_default_on_file": "N",
        }
        _, frame = services.application_from_cleaned_data(self.bundle, cleaned)
        self.assertEqual(frame.columns.tolist(), FEATURES)
        self.assertAlmostEqual(frame.iloc[0]["loan_percent_income"], 0.1231)

    def test_artifact_allowlist_blocks_unknown_files(self) -> None:
        self.assertIsNone(services.report_artifact_path("../../README.md"))
        self.assertIsNotNone(services.report_artifact_path("calibration_curve.png"))

    def test_threshold_selection_uses_lowest_cost(self) -> None:
        y_true = pd.Series([0, 0, 1, 1])
        probabilities = np.array([0.1, 0.4, 0.45, 0.9])
        table = build_threshold_table(y_true, probabilities)
        threshold = choose_business_threshold(table)
        selected = table.loc[table["threshold"].eq(threshold)].iloc[0]
        self.assertEqual(selected["business_cost"], table["business_cost"].min())

    def test_metrics_include_probability_quality(self) -> None:
        metrics = evaluate_predictions(
            pd.Series([0, 0, 1, 1]),
            np.array([0.05, 0.2, 0.8, 0.95]),
        )
        self.assertIn("average_precision", metrics)
        self.assertIn("brier_score", metrics)

    def test_cleaned_training_data_removes_duplicates_and_outliers(self) -> None:
        data = load_credit_data()
        self.assertEqual(data.duplicated().sum(), 0)
        self.assertEqual(int((data["person_age"] > 100).sum()), 0)
        self.assertEqual(int((data["person_emp_length"] > 60).sum()), 0)


class DashboardViewTests(TestCase):
    def valid_payload(self) -> dict[str, str]:
        return {
            "person_age": "30",
            "person_income": "65000",
            "person_emp_length": "5",
            "person_home_ownership": "RENT",
            "loan_amnt": "8000",
            "loan_intent": "PERSONAL",
            "cb_person_cred_hist_length": "6",
            "cb_person_default_on_file": "N",
        }

    def test_health_and_readiness(self) -> None:
        health = self.client.get(reverse("health"))
        ready = self.client.get(reverse("readiness"))
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json(), {"status": "ok"})
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.json()["status"], "ready")

    @patch("app.services.assessment_result")
    def test_get_assessment_does_not_score(self, assessment_result) -> None:
        response = self.client.get(reverse("assessment"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["has_result"])
        assessment_result.assert_not_called()
        self.assertContains(response, "No prediction is generated before submission")

    def test_invalid_post_shows_errors_without_audit_record(self) -> None:
        payload = self.valid_payload()
        payload["person_income"] = "0"
        response = self.client.post(reverse("assessment"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["has_result"])
        self.assertEqual(PredictionAudit.objects.count(), 0)
        self.assertContains(response, "Ensure this value is greater than or equal to 1")

    @patch("app.services.applicant_explanations")
    def test_valid_post_scores_and_writes_privacy_preserving_audit(self, explanations) -> None:
        explanations.return_value = (
            [
                {
                    "factor": "Income",
                    "detail": "Test explanation",
                    "impact": "Lowers model risk",
                    "class": "positive",
                }
            ],
            "Test method",
        )
        response = self.client.post(reverse("assessment"), self.valid_payload())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["has_result"])
        audit = PredictionAudit.objects.get()
        self.assertEqual(len(audit.feature_digest), 64)
        self.assertEqual(audit.model_version, "2.0.0")

    def test_report_downloads_and_allowlist(self) -> None:
        self.assertEqual(self.client.get(reverse("download-summary-csv")).status_code, 200)
        self.assertEqual(self.client.get(reverse("download-summary-pdf")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("report-artifact", args=["calibration_curve.png"])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("report-artifact", args=["unknown.txt"])).status_code,
            404,
        )

    def test_model_manifest_matches_bundle(self) -> None:
        manifest = json.loads((services.PROJECT_ROOT / "models" / "model_manifest.json").read_text())
        bundle = services.load_model_bundle()
        self.assertEqual(manifest["model_version"], bundle["model_version"])
        self.assertEqual(manifest["data_sha256"], bundle["data_sha256"])

    @override_settings(SCORING_API_KEY="test-api-key")
    def test_scoring_api_requires_authentication(self) -> None:
        response = self.client.post(
            reverse("score-api"),
            data=json.dumps(self.valid_payload()),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    @override_settings(SCORING_API_KEY="test-api-key")
    def test_scoring_api_validates_payload(self) -> None:
        payload = self.valid_payload()
        payload["person_income"] = "0"
        response = self.client.post(
            reverse("score-api"),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_API_KEY="test-api-key",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("person_income", response.json()["fields"])

    @override_settings(SCORING_API_KEY="test-api-key")
    def test_scoring_api_returns_versioned_result(self) -> None:
        response = self.client.post(
            reverse("score-api"),
            data=json.dumps(self.valid_payload()),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer test-api-key",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["model_version"], "2.0.0")
        self.assertIn("probability", response.json())
