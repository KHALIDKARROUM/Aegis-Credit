from __future__ import annotations

from typing import Any

from django import forms
from django.core.exceptions import ValidationError


class ApplicantAssessmentForm(forms.Form):
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
        label="Employment length",
        min_value=0,
        max_value=60,
        widget=forms.NumberInput(attrs={"step": 0.5, "inputmode": "decimal"}),
    )
    person_home_ownership = forms.ChoiceField(label="Home ownership")
    loan_amnt = forms.IntegerField(
        label="Loan amount",
        min_value=500,
        max_value=500_000,
        widget=forms.NumberInput(attrs={"step": 500, "inputmode": "numeric"}),
    )
    loan_intent = forms.ChoiceField(label="Loan intent")
    cb_person_cred_hist_length = forms.IntegerField(
        label="Credit history length",
        min_value=0,
        max_value=50,
        widget=forms.NumberInput(attrs={"inputmode": "numeric"}),
    )
    cb_person_default_on_file = forms.ChoiceField(label="Prior default on file")

    field_order = [
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
        **kwargs: Any,
    ) -> None:
        self.bundle = bundle
        reference = bundle["feature_reference"]
        options = reference["categorical_options"]
        medians = reference["numeric_medians"]
        modes = reference["categorical_modes"]

        kwargs.setdefault(
            "initial",
            {
                "person_age": round(medians["person_age"]),
                "person_income": round(medians["person_income"]),
                "person_emp_length": round(medians["person_emp_length"], 1),
                "person_home_ownership": modes["person_home_ownership"],
                "loan_amnt": round(medians["loan_amnt"]),
                "loan_intent": modes["loan_intent"],
                "cb_person_cred_hist_length": round(medians["cb_person_cred_hist_length"]),
                "cb_person_default_on_file": modes["cb_person_default_on_file"],
            },
        )
        super().__init__(*args, **kwargs)

        for name in (
            "person_home_ownership",
            "loan_intent",
            "cb_person_default_on_file",
        ):
            self.fields[name].choices = [(value, value.replace("_", " ").title()) for value in options[name]]

        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"

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
                "Employment length cannot be longer than the applicant's working-age history.",
            )
        if age is not None and credit_history is not None and credit_history > max(age - 16, 0):
            self.add_error(
                "cb_person_cred_hist_length",
                "Credit history cannot be longer than the applicant's adult credit history.",
            )
        if income and amount and amount / income > 1.5:
            raise ValidationError(
                "The requested loan is more than 150% of annual income. Review the values before scoring."
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
            "person_emp_length": "Employment length",
            "loan_amnt": "Loan amount",
            "loan_percent_income": "Loan-to-income ratio",
            "cb_person_cred_hist_length": "Credit history length",
        }
        for feature, limit in bounds.items():
            value = float(values[feature])
            if value < limit["minimum"] or value > limit["maximum"]:
                warnings.append(
                    f"{labels.get(feature, feature)} is outside the central 99% of the training data."
                )
        return warnings
