# Changelog

## 2.1.0 — 2026-06-26

- added blank-by-default assessment inputs and an explicit demo-data action;
- corrected risk bands so normal and enhanced manual-review paths are reachable;
- added durable cases, statuses, notes, assignments, overrides, and printable views;
- added CSV/Excel batch loading with row-level validation and result downloads;
- added analyst, reviewer, administrator, login, and administration workflows;
- added keyed audit fingerprints, idempotency keys, and API rate limiting;
- added operational monitoring and financially explicit threshold scenarios;
- added PostgreSQL, Docker Compose, Render database, retention, and bootstrap tooling;
- separated model selection, calibration, threshold selection, and final testing;
- built drift baselines from training rows only and added external validation tooling;
- selected calibrated Gradient Boosting as the champion after challenger comparison;
- added code licensing and explicit unresolved dataset-provenance documentation.

## 2.0.0 — 2026-06-25

- separated training, validation/calibration, and final test evaluation;
- added calibrated probabilities and validation-selected thresholding;
- excluded lender-assigned grade and interest rate from application-time scoring;
- excluded age from scoring while retaining it for validation and monitoring;
- added model metadata, artifact manifest, calibration, and age-group diagnostics;
- replaced silent input clamping with validated Django forms;
- stopped predictions and SHAP work on initial page load;
- added privacy-preserving prediction audit records;
- added liveness/readiness endpoints, tests, CI, and deployment hardening;
- refreshed the assessment experience, accessibility, and responsive layout.
