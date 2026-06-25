# BankRisk Compass Model Card

## Model identity

- Version: `2.0.0`
- Model: calibrated Random Forest classifier
- Intended stage: application-time screening
- Target: `loan_status` (`1` means default)
- Output: calibrated probability of default plus a review threshold

The serialized bundle and `models/model_manifest.json` contain the training timestamp,
Git commit, dataset hash, feature contract, dependency versions, and artifact hash.

## Intended use

The model is a learning and decision-support system for demonstrating credit-risk
modeling. It may help prioritize applications for human review.

It must not be used as:

- an autonomous approval or decline engine;
- an adverse-action notice generator;
- a substitute for legal, compliance, or independent model validation;
- a production lending system without representative data and monitoring.

## Feature contract

Application-time scoring features:

- annual income;
- employment length;
- home ownership;
- requested loan amount;
- loan intent;
- credit-history length;
- prior-default indicator;
- derived loan-to-income ratio.

`loan_grade` and `loan_int_rate` are excluded from applicant scoring because they
may be assigned by the lender after underwriting starts.

Age is collected for plausibility validation and subgroup monitoring, but is
excluded from the score itself.

## Development and evaluation

Data is split into training, validation/calibration, and final test sets.

- Hyperparameter fitting occurs on training data.
- Probability calibration and threshold selection occur on validation data.
- Final metrics are measured once on the untouched test set.

Current final-test results are stored in `reports/final_model_metrics.csv`.
Calibration and age-group diagnostics are stored in `reports/`.

## Limitations

- The public dataset may not represent a particular bank, geography, product, or period.
- Protected-class attributes required for a complete fair-lending assessment are unavailable.
- Some age groups have very small sample sizes.
- Relationships in historical data may change over time.
- The 5:1 error-cost ratio is illustrative and requires business approval.
- Local SHAP factors explain model behavior; they are not automatically compliant
  adverse-action reasons.

## Required controls before production

- independent model validation;
- legal and fair-lending review;
- approved adverse-action reason mapping;
- authenticated access and durable audit storage;
- drift, calibration, performance, and subgroup monitoring;
- documented override and rollback procedures;
- periodic threshold and cost-assumption review.
