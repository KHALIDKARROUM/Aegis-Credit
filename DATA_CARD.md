# Aegis-Credit Data Card

## Dataset

File: `data/credit_risk.csv`

The repository contains 32,581 source rows and 12 columns. Training removes exact
duplicates and replaces implausible ages above 100 and employment lengths above
60 years with missing values before pipeline imputation.

## Fields

- borrower: age, income, employment length, home ownership;
- loan: amount, interest rate, grade, intent, loan-to-income ratio;
- credit history: prior-default flag and credit-history length;
- target: `loan_status`.

## Data quality

- The target is imbalanced, with approximately 22% defaults.
- Employment length and interest rate contain missing values.
- A small number of age and employment values are implausible.
- Loan-to-income ratio is always re-derived from amount and income by the same
  versioned feature contract in training, validation, monitoring, and serving.
- The stored source ratio disagrees with that derivation on many rows. The
  checked-in 2.1.0 artifact predates the correction and remains demo-only; a
  corrected release must use version 2.2.0 or later.

## Source and licensing

The original upstream source and license are not documented in this repository.
That provenance must be established before redistribution or operational use.
The project MIT license does not cover `data/credit_risk.csv`.

## Representation and fairness limits

The dataset does not contain the full set of protected-class and product-context
fields needed for a complete fair-lending analysis. Age is excluded from scoring
and reported only as a limited monitoring slice. Small older-age groups make
those results unstable.

## Privacy

The included dataset appears de-identified, but its provenance should be reviewed.
The scoring audit stores a keyed digest and decision metadata without raw input
values. A separate case record stores only the model input fields needed for
staff review, encrypted at the application layer. Applicant references are also
encrypted and have a keyed, exact-match lookup digest. Immutable review,
legal-hold, outcome, monitoring, and deletion-receipt records are retained under
the configured policy. This is data minimization, not anonymization.

## Refresh and monitoring

For production use, define:

- an approved source and extraction date;
- schema and range checks;
- data-retention rules;
- drift baselines and alert thresholds;
- target-label maturity and delayed-performance reporting;
- periodic representativeness reviews.

Feature-reference ranges and drift baselines are generated from training rows
only. The final test set does not contribute to operational baselines.
Mature outcomes must be imported through the controlled outcome workflow; the
monitoring page does not infer performance from unlabeled score volume.
