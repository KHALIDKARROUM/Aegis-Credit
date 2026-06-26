# BankRisk Compass Final Report

## Final Model

The final model is a calibrated, leakage-safe Gradient Boosting classifier. Missing values, scaling, and one-hot encoding are fitted only on training data. Model selection, probability calibration, and threshold selection use separate data partitions; the final metrics below are measured once on an untouched test set.

Application-time scoring intentionally excludes lender-assigned fields (`loan_grade` and `loan_int_rate`) to avoid using information that may not exist when an applicant is first assessed.
Age is also excluded from the probability model; it is retained only for input plausibility checks and subgroup monitoring.

Data split:

- Training: 19,449 rows
- Model selection: 2,593 rows
- Probability calibration: 1,945 rows
- Threshold selection: 1,945 rows
- Final test: 6,484 rows

Selected model parameters:

```text
{'n_estimators': 100, 'learning_rate': 0.1, 'max_depth': 3, 'min_samples_leaf': 1}
```

## Default 0.50 Threshold Results

| Metric | Score |
|---|---:|
| Accuracy | 0.884 |
| Precision | 0.880 |
| Recall | 0.543 |
| F1-score | 0.672 |
| ROC-AUC | 0.881 |
| Average precision | 0.791 |
| Brier score | 0.089 |

## Business Threshold Results

The selected business threshold is **0.21**. It assumes a false negative is 5x more costly than a false positive:

- False negative: a risky borrower is approved.
- False positive: a safer borrower is rejected or sent to manual review.

| Metric | Score |
|---|---:|
| Accuracy | 0.828 |
| Precision | 0.582 |
| Recall | 0.755 |
| F1-score | 0.657 |
| ROC-AUC | 0.881 |
| Average precision | 0.791 |
| Brier score | 0.089 |
| False positives | 770 |
| False negatives | 347 |
| Business cost | 2505 |

## Interpretation

The model is a decision-support tool, not an autonomous approval system. The business threshold prioritizes recall for defaults while monitoring the number of safer applicants routed to review. Age-group diagnostics and calibration reports are generated for governance review, but they do not replace a complete fair-lending assessment using legally appropriate protected-class data.
