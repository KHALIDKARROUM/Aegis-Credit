# Staff User Guide

## Single assessment

1. Open **New assessment**.
2. Enter every required field. New forms are intentionally blank.
3. Use **Load demo example** only for demonstrations.
4. Select **Show assessment**.
5. Review the probability, risk band, recommendation, warnings, and influencing factors.
6. Open the saved case to record a human review.

Do not enter applicant names, account numbers, government identifiers, or free
text containing sensitive personal data in the application reference.

## Case review

Reviewers can change status, add notes, and override the model recommendation.
An override reason is mandatory. The model output remains visible so the human
decision can be audited without rewriting model history.

## Batch load

Download the template from **Batch load**. Upload CSV or Excel. Invalid rows are
not scored. Download the result CSV to correct errors or reconcile case IDs.

## Monitoring

Monitoring shows score volume, source, risk mix, reviewed cases, override rate,
and the most recently generated offline drift report.

## Business policy

The scenario calculator estimates:

- loss from missed defaults;
- manual-review cost;
- opportunity cost for safer applicants routed to review.

It does not change live scoring. Approved policy changes require retraining,
validation, a new artifact, and deployment approval.
