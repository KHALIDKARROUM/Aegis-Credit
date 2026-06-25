# Changelog

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
