# Staff User Guide

The workspace badge identifies a local demonstration, development workspace, or
controlled workspace. Never treat a local-demo score as an approved lending
decision. Navigation is role-aware: analysts see applicant workflows;
reviewers and administrators also see monitoring, policy, and governance pages;
legal officers see only the case-preservation and monitoring areas assigned to
their role.

## Single assessment

1. Open **New assessment**.
2. Enter every required field. New forms are intentionally blank.
3. Use **Load demo example** only for demonstrations.
4. Select **Show assessment**.
5. Review the probability, risk band, recommendation, warnings, and influencing factors.
6. Open the saved case to record a human review.

Do not enter applicant names, account numbers, government identifiers, or free
text containing sensitive personal data in the application reference.

Age is collected for plausibility checks but is excluded from the scoring model
and is not retained in the saved case. It appears in the submitted-detail view
only so the operator can verify what was entered.

## Case review

Reviewers can change status, add notes, and override the model recommendation. 
An override reason is mandatory. The model output remains visible so the human
decision can be audited without rewriting model history.

Until a reviewer saves a review, the case displays **Not yet reviewed**. “No
override recorded” means the reviewer did not replace the model guidance; it
must not be read as an autonomous approval. Use assignment and review-timing
filters when those controls are configured for the deployment.

Typical statuses are:

- **New** — no review has started;
- **In review** — a staff member is actively checking the case;
- **Referred** — additional or senior review is required;
- **Cleared** — the screening concern has been addressed for the next workflow step;
- **Closed** — no further review work is expected.

A legal hold suspends routine retention deletion. Add or release one only under
the organization’s approved legal process. Legal officers and administrators
must use the case’s **Legal hold** panel and record a substantive reason and
formal ticket reference. Each placement or release is retained as an immutable
case event.

## Batch load

Download the template from **Batch load**. Upload CSV or Excel. Invalid rows are
not scored. Scored rows can still carry unusual-input warnings: review those
warnings on the result page before continuing. Download the result CSV to
correct errors or reconcile case IDs.

Do not close the browser during synchronous local-demo processing. Shared
deployments expose progress while background processing is active. Retry a
failed batch when the failure was transient; correct and upload a new source
file when its data was invalid. Completed durable rows are retained, but a
partial display is not a complete batch result.

## Monitoring

Monitoring shows score volume, source, risk mix, reviewed cases, override rate,
and persisted, recomputed drift evidence. Check the report generation time,
model version, incoming sample size, and freshness status before interpreting it. A
missing, stale, or failed report requires follow-up with the monitoring owner;
“no alert” is not equivalent to fresh evidence.

Use **Record monitoring follow-up** to acknowledge, escalate, or resolve a run
with a substantive immutable note. A resolution records the workflow action; it
does not erase the original alert or replace corrective evidence.

## Business policy

The scenario calculator estimates:

- loss from missed defaults;
- manual-review cost;
- opportunity cost for safer applicants routed to review.

It does not change live scoring. Approved policy changes require retraining,
validation, a new artifact, and deployment approval.

Name the scenario and save it as a draft to retain its assumptions, source model
version, and calculated recommendation. An administrator records an approval or
rejection with a substantive rationale. That governance status still does not
activate the threshold: compare expected review volume with actual staffing
capacity, then complete independent validation and the model-release process.

## Reports

The Reports page combines summary metrics with downloadable source artifacts.
Verify the model version, trained date, report generation metadata, and release
status before approval. The summary PDF is convenient for reading; CSV and HTML
tables should remain available when an accessible machine-readable format is
needed. The saved explanation factors are not approved adverse-action reasons.

## API reference

The API page is a static quick reference with request, response, and error
examples. Import `/api/v1/openapi.json` into an approved OpenAPI viewer when an
interactive console or generated client is required. Keep API keys out of URLs
and logs, and reuse an idempotency key only for a retry of the same logical
request.

## Keyboard and assistive-technology use

Use **Skip to main content** to bypass navigation. Tables have descriptive
captions and can scroll horizontally at narrow widths. Form hints and errors are
programmatically associated with their controls; after a validation error,
review every field marked invalid before resubmitting.
