# BankRisk Compass Model Card

## Identity

- Version: `2.1.0`
- Champion: calibrated Gradient Boosting classifier
- Stage: application-time screening and human review prioritization
- Target: `loan_status`, where `1` represents default
- Output: calibrated probability, risk band, and screening recommendation

The serialized bundle and `models/model_manifest.json` include the training
timestamp, Git state, data hash, model hash, feature contract, split sizes, and
runtime versions.

## Intended use

The model may support demonstrations, analyst training, portfolio development,
and controlled pilot review queues.

It must not:

- autonomously approve or decline credit;
- generate adverse-action notices;
- replace affordability, identity, policy, fraud, or compliance checks;
- be used operationally without representative data and independent validation.

## Feature contract

Scored features:

- annual income;
- employment length;
- home ownership;
- requested amount;
- loan intent;
- credit-history length;
- prior-default indicator;
- derived loan-to-income ratio.

Loan grade and interest rate are excluded because they may be assigned after
underwriting begins. Age is collected for plausibility validation and limited
monitoring but is excluded from the probability model.

## Development design

Exact duplicates are removed and implausible age/employment values are replaced
with missing values before pipeline imputation. Preprocessing is fitted only on
training rows.

Non-overlapping partitions:

- training: 19,449;
- model selection: 2,593;
- calibration: 1,945;
- threshold selection: 1,945;
- final test: 6,484.

Logistic Regression, tuned Random Forest, and Gradient Boosting candidates are
calibrated and thresholded before comparison. The champion is selected on the
model-selection partition using business cost, followed by F1 and ROC-AUC.

## Final-test performance

| Policy | Accuracy | Precision | Recall | F1 | ROC-AUC | Brier |
|---|---:|---:|---:|---:|---:|---:|
| 0.50 | 0.884 | 0.880 | 0.543 | 0.672 | 0.881 | 0.089 |
| 0.21 | 0.828 | 0.582 | 0.755 | 0.657 | 0.881 | 0.089 |

The `0.21` threshold uses an illustrative 5:1 false-negative/false-positive cost
ratio. It routes approximately 28.4% of final-test applications to review.

## Explanations

Local SHAP factors describe the behavior of the underlying tree model. They are
not automatically specific, accurate, validated adverse-action reasons.

If SHAP is unavailable, the interface shows separately labeled review checks.
Fallback checks must never be represented as model-derived reasons.

## Fairness and representation

Age is excluded from scoring. Age-group reports are diagnostic only. The oldest
test groups contain very few observations, and the dataset does not contain the
protected-class and product context required for a complete fair-lending review.

## Required production controls

- organization-specific data and out-of-time/external validation;
- approved expected-loss and profitability assumptions;
- independent model validation and challenger review;
- validated reason-code mapping and legal review;
- subgroup, drift, calibration, performance, and override monitoring;
- version approval, rollback, incident, backup, and recovery procedures;
- periodic review of thresholds, risk bands, retention, and access.
