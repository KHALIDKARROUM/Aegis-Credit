# BankRisk Compass Data Card

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
- Loan-to-income ratio is checked against amount and income during assessment.

## Source and licensing

The original upstream source and license are not documented in this repository.
That provenance must be established before redistribution or operational use.

## Representation and fairness limits

The dataset does not contain the full set of protected-class and product-context
fields needed for a complete fair-lending analysis. Age is excluded from scoring
and reported only as a limited monitoring slice. Small older-age groups make
those results unstable.

## Privacy

The included dataset appears de-identified, but its provenance should be reviewed.
The application audit table stores a SHA-256 digest of validated model inputs and
the prediction outcome; it does not store the raw applicant fields.

## Refresh and monitoring

For production use, define:

- an approved source and extraction date;
- schema and range checks;
- data-retention rules;
- drift baselines and alert thresholds;
- target-label maturity and delayed-performance reporting;
- periodic representativeness reviews.
