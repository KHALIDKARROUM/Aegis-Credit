# Security Policy

## Supported version

Security fixes are applied to the current `main` branch.

## Reporting

Do not publish secrets, applicant data, or exploitable details in a public issue.
Report the problem privately to the repository owner with reproduction steps and
the affected version.

## Operational guidance

- Set a long random `SECRET_KEY` whenever `DEBUG=False`.
- Serve the deployed application only through HTTPS.
- Restrict dashboard access before using non-demo data.
- Never commit applicant records, credentials, or environment files.
- Treat pickle/joblib model artifacts as trusted-code artifacts. Load only files
  produced by the controlled training pipeline and verify `models/model_manifest.json`.
- Keep Python and pinned dependencies updated after compatibility testing.

This repository is a demonstration system and has not undergone an external
penetration test.
