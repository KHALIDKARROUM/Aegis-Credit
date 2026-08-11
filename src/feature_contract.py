"""Canonical feature construction shared by training, validation, and serving.

The source dataset contains a ``loan_percent_income`` column, but production
requests contain the raw loan amount and annual income.  Treating the stored
ratio as authoritative during training creates training-serving skew whenever
the three values disagree.  This module makes the raw fields authoritative and
is intentionally independent of Django so every execution path can reuse it.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


FEATURE_CONTRACT_VERSION = "1.0.0"
TARGET = "loan_status"
LOAN_PERCENT_INCOME_DECIMALS = 4

RAW_NUMERIC_FEATURES = [
    "person_income",
    "person_emp_length",
    "loan_amnt",
    "cb_person_cred_hist_length",
]

DERIVED_NUMERIC_FEATURES = ["loan_percent_income"]

NUMERIC_FEATURES = [
    "person_income",
    "person_emp_length",
    "loan_amnt",
    "loan_percent_income",
    "cb_person_cred_hist_length",
]

CATEGORICAL_FEATURES = [
    "person_home_ownership",
    "loan_intent",
    "cb_person_default_on_file",
]

RAW_MODEL_FEATURES = RAW_NUMERIC_FEATURES + CATEGORICAL_FEATURES
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES

EXCLUDED_LENDER_ASSIGNED_FEATURES = ["loan_int_rate", "loan_grade"]
EXCLUDED_POLICY_FEATURES = ["person_age"]
FORM_NUMERIC_FEATURES = ["person_age"] + NUMERIC_FEATURES


class FeatureContractError(ValueError):
    """Raised when raw model inputs cannot satisfy the feature contract."""


def _require_columns(data: pd.DataFrame, columns: list[str]) -> None:
    missing = sorted(set(columns) - set(data.columns))
    if missing:
        raise FeatureContractError(
            f"Data is missing raw model input columns: {', '.join(missing)}"
        )


def _numeric_series(data: pd.DataFrame, column: str) -> pd.Series:
    try:
        return pd.to_numeric(data[column], errors="raise").astype(float)
    except (TypeError, ValueError) as exc:
        raise FeatureContractError(f"{column} must contain numeric values.") from exc


def canonical_loan_percent_income(data: pd.DataFrame) -> pd.Series:
    """Return the canonical loan-to-income ratio from raw application fields."""

    _require_columns(data, ["person_income", "loan_amnt"])
    income = _numeric_series(data, "person_income")
    loan_amount = _numeric_series(data, "loan_amnt")

    invalid_income = income.isna() | ~np.isfinite(income) | income.le(0)
    invalid_amount = loan_amount.isna() | ~np.isfinite(loan_amount) | loan_amount.lt(0)
    if invalid_income.any() or invalid_amount.any():
        details = []
        if invalid_income.any():
            details.append("person_income must be finite and greater than zero")
        if invalid_amount.any():
            details.append("loan_amnt must be finite and non-negative")
        raise FeatureContractError("; ".join(details) + ".")

    ratio = (loan_amount / income).round(LOAN_PERCENT_INCOME_DECIMALS)
    ratio.name = "loan_percent_income"
    return ratio


def with_canonical_derived_features(data: pd.DataFrame) -> pd.DataFrame:
    """Copy ``data`` and overwrite derived fields from authoritative raw inputs."""

    output = data.copy()
    output["loan_percent_income"] = canonical_loan_percent_income(output)
    return output


def model_feature_frame(data: pd.DataFrame) -> pd.DataFrame:
    """Build an ordered model frame using the canonical serving-time contract."""

    _require_columns(data, RAW_MODEL_FEATURES)
    output = with_canonical_derived_features(data)
    for feature in RAW_NUMERIC_FEATURES:
        numeric = _numeric_series(output, feature)
        non_finite = numeric.notna() & ~np.isfinite(numeric)
        if non_finite.any():
            raise FeatureContractError(f"{feature} contains non-finite values.")
        output[feature] = numeric
    return output.loc[:, FEATURES]


def validate_categorical_contract(
    data: pd.DataFrame,
    allowed_options: dict[str, list[str]],
) -> None:
    """Reject values that the serving form would not accept."""

    _require_columns(data, CATEGORICAL_FEATURES)
    violations: list[str] = []
    for feature in CATEGORICAL_FEATURES:
        if data[feature].isna().any():
            violations.append(f"{feature}=<missing>")
        allowed = {str(value) for value in allowed_options.get(feature, [])}
        observed = set(data[feature].dropna().astype(str).unique().tolist())
        unknown = sorted(observed - allowed)
        if unknown:
            violations.append(f"{feature}={unknown}")
    if violations:
        raise FeatureContractError(
            "Data contains categories outside the serving contract: "
            + "; ".join(violations)
        )


def validate_binary_target(values: pd.Series, *, name: str = TARGET) -> pd.Series:
    """Validate and return a non-null binary integer outcome series."""

    if values.isna().any():
        raise FeatureContractError(f"{name} contains missing outcomes.")
    try:
        numeric = pd.to_numeric(values, errors="raise")
    except (TypeError, ValueError) as exc:
        raise FeatureContractError(f"{name} must contain binary 0/1 outcomes.") from exc
    observed: set[Any] = set(numeric.unique().tolist())
    if not observed or not observed.issubset({0, 1}) or len(observed) < 2:
        raise FeatureContractError(
            f"{name} must contain both binary outcome classes 0 and 1."
        )
    return numeric.astype(int)
