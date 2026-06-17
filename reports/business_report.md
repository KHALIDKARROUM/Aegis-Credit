# BankRisk Compass Final Report

## Final Model

The final model is a leakage-safe Random Forest classifier wrapped in a scikit-learn Pipeline. Missing values, scaling, and one-hot encoding are fitted only on the training data through a ColumnTransformer.

Best hyperparameters:

```text
{'classifier__max_depth': None, 'classifier__min_samples_leaf': 1, 'classifier__n_estimators': 200}
```

## Default 0.50 Threshold Results

| Metric | Score |
|---|---:|
| Accuracy | 0.934 |
| Precision | 0.974 |
| Recall | 0.715 |
| F1-score | 0.825 |
| ROC-AUC | 0.931 |

## Business Threshold Results

The selected business threshold is **0.26**. It assumes a false negative is 5x more costly than a false positive:

- False negative: a risky borrower is approved.
- False positive: a safer borrower is rejected or sent to manual review.

| Metric | Score |
|---|---:|
| Accuracy | 0.913 |
| Precision | 0.810 |
| Recall | 0.784 |
| F1-score | 0.797 |
| ROC-AUC | 0.931 |
| False positives | 260 |
| False negatives | 306 |
| Business cost | 1790 |

## Interpretation

The model performs strongly at ranking applicants by default risk, but bank decisions should not use accuracy alone. In credit risk, the cost of approving a borrower who defaults is usually higher than the cost of sending a borderline safe borrower to manual review. The business threshold therefore prioritizes recall for defaults while still monitoring precision to avoid rejecting too many viable customers.
