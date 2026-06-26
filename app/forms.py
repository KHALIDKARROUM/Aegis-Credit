from __future__ import annotations

import uuid
from typing import Any

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError

from .models import AssessmentCase


class ApplicantAssessmentForm(forms.Form):
    request_id = forms.UUIDField(
        required=False,
        widget=forms.HiddenInput(),
    )
    applicant_reference = forms.CharField(
        label="Application reference",
        required=False,
        max_length=80,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "placeholder": "Optional internal reference",
            }
        ),
    )
    person_age = forms.IntegerField(
        label="Age",
        min_value=18,
        max_value=100,
        widget=forms.NumberInput(attrs={"inputmode": "numeric", "autocomplete": "off"}),
    )
    person_income = forms.IntegerField(
        label="Annual income",
        min_value=1,
        max_value=2_000_000,
        widget=forms.NumberInput(attrs={"step": 1000, "inputmode": "numeric"}),
    )
    person_emp_length = forms.FloatField(
        label="Years employed",
        min_value=0,
        max_value=60,
        widget=forms.NumberInput(attrs={"step": 0.5, "inputmode": "decimal"}),
    )
    person_home_ownership = forms.ChoiceField(label="Housing situation")
    loan_amnt = forms.IntegerField(
        label="Loan amount",
        min_value=500,
        max_value=500_000,
        widget=forms.NumberInput(attrs={"step": 500, "inputmode": "numeric"}),
    )
    loan_intent = forms.ChoiceField(label="Purpose of the loan")
    cb_person_cred_hist_length = forms.IntegerField(
        label="Years of credit history",
        min_value=0,
        max_value=50,
        widget=forms.NumberInput(attrs={"inputmode": "numeric"}),
    )
    cb_person_default_on_file = forms.ChoiceField(label="Previous default recorded?")

    field_order = [
        "request_id",
        "applicant_reference",
        "person_age",
        "person_income",
        "person_emp_length",
        "person_home_ownership",
        "loan_amnt",
        "loan_intent",
        "cb_person_cred_hist_length",
        "cb_person_default_on_file",
    ]

    def __init__(
        self,
        *args: Any,
        bundle: dict[str, Any],
        use_demo: bool = False,
        **kwargs: Any,
    ) -> None:
        self.bundle = bundle
        reference = bundle["feature_reference"]
        options = reference["categorical_options"]
        medians = reference["numeric_medians"]
        modes = reference["categorical_modes"]

        initial = {"request_id": uuid.uuid4()}
        if use_demo:
            initial.update(
                {
                "person_age": round(medians["person_age"]),
                "person_income": round(medians["person_income"]),
                "person_emp_length": round(medians["person_emp_length"], 1),
                "person_home_ownership": modes["person_home_ownership"],
                "loan_amnt": round(medians["loan_amnt"]),
                "loan_intent": modes["loan_intent"],
                "cb_person_cred_hist_length": round(medians["cb_person_cred_hist_length"]),
                "cb_person_default_on_file": modes["cb_person_default_on_file"],
                }
            )
        kwargs.setdefault("initial", initial)
        super().__init__(*args, **kwargs)

        choice_labels = {
            "person_home_ownership": {
                "RENT": "Renting",
                "MORTGAGE": "Mortgage",
                "OWN": "Own home",
                "OTHER": "Other",
            },
            "loan_intent": {
                "DEBTCONSOLIDATION": "Debt consolidation",
                "EDUCATION": "Education",
                "HOMEIMPROVEMENT": "Home improvement",
                "MEDICAL": "Medical expenses",
                "PERSONAL": "Personal expenses",
                "VENTURE": "Business",
            },
            "cb_person_default_on_file": {
                "N": "No",
                "Y": "Yes",
            },
        }
        for name in choice_labels:
            choices = [
                (value, choice_labels[name].get(value, value.replace("_", " ").title()))
                for value in options[name]
            ]
            self.fields[name].choices = choices if use_demo else [("", "Select…"), *choices]

        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"
        self.fields["request_id"].widget.attrs.pop("class", None)

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        age = cleaned.get("person_age")
        employment = cleaned.get("person_emp_length")
        credit_history = cleaned.get("cb_person_cred_hist_length")
        income = cleaned.get("person_income")
        amount = cleaned.get("loan_amnt")

        if age is not None and employment is not None and employment > max(age - 14, 0):
            self.add_error(
                "person_emp_length",
                "Years employed cannot be longer than the applicant's working-age history.",
            )
        if age is not None and credit_history is not None and credit_history > max(age - 16, 0):
            self.add_error(
                "cb_person_cred_hist_length",
                "Credit history cannot be longer than the applicant's adult credit history.",
            )
        if income and amount and amount / income > 1.5:
            raise ValidationError(
                "The requested loan is more than 150% of annual income. Please check the values before continuing."
            )

        return cleaned

    def distribution_warnings(self) -> list[str]:
        if not self.is_valid():
            return []

        warnings: list[str] = []
        bounds = self.bundle["feature_reference"].get("numeric_bounds", {})
        values = dict(self.cleaned_data)
        values["loan_percent_income"] = values["loan_amnt"] / values["person_income"]
        labels = {
            "person_age": "Age",
            "person_income": "Income",
            "person_emp_length": "Years employed",
            "loan_amnt": "Loan amount",
            "loan_percent_income": "Loan-to-income ratio",
            "cb_person_cred_hist_length": "Credit history length",
        }
        for feature, limit in bounds.items():
            value = float(values[feature])
            if value < limit["minimum"] or value > limit["maximum"]:
                warnings.append(
                    f"{labels.get(feature, feature)} is outside the usual range seen in past applications. Please verify it."
                )
        return warnings


class CaseReviewForm(forms.ModelForm):
    class Meta:
        model = AssessmentCase
        fields = [
            "status",
            "reviewer_notes",
            "override_decision",
            "override_reason",
            "legal_hold",
        ]
        widgets = {
            "reviewer_notes": forms.Textarea(attrs={"rows": 4}),
            "override_reason": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        if cleaned.get("override_decision") and not str(cleaned.get("override_reason", "")).strip():
            self.add_error(
                "override_reason",
                "Explain why the human reviewer is overriding the model recommendation.",
            )
        return cleaned


class BatchUploadForm(forms.Form):
    file = forms.FileField(
        label="Applicant file",
        help_text="Upload CSV or Excel with the documented input columns.",
    )

    def clean_file(self) -> Any:
        upload = self.cleaned_data["file"]
        suffix = upload.name.lower().rsplit(".", maxsplit=1)[-1] if "." in upload.name else ""
        if suffix not in {"csv", "xlsx"}:
            raise ValidationError("Upload a .csv or .xlsx file.")
        if upload.size > settings.MAX_UPLOAD_BYTES:
            raise ValidationError(
                f"The file is larger than the {settings.MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit."
            )
        return upload


class BusinessEconomicsForm(forms.Form):
    average_exposure = forms.DecimalField(
        label="Average approved loan",
        min_value=100,
        max_value=10_000_000,
        initial=10_000,
        decimal_places=2,
    )
    loss_given_default = forms.DecimalField(
        label="Loss given default",
        min_value=0,
        max_value=1,
        initial=0.60,
        decimal_places=3,
        help_text="Share of exposure lost after recoveries, from 0 to 1.",
    )
    annual_margin = forms.DecimalField(
        label="Annual contribution margin",
        min_value=0,
        max_value=1,
        initial=0.08,
        decimal_places=3,
        help_text="Expected net margin on a performing loan, from 0 to 1.",
    )
    review_cost = forms.DecimalField(
        label="Manual review cost",
        min_value=0,
        max_value=100_000,
        initial=35,
        decimal_places=2,
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"
