# Operations Guide

## Production baseline

- Set `DEBUG=False`, `LOGIN_REQUIRED=True`, and strong independent secrets.
- Use PostgreSQL through `DATABASE_URL`.
- Run migrations and `bootstrap_roles` during deployment.
- Create named analyst/reviewer accounts; do not share credentials.
- Restrict admin access and rotate API keys.
- Schedule retention, backup, restore, dependency, and security reviews.

## Health checks

- `/healthz/` confirms the web process responds.
- `/readyz/` verifies the model integrity manifest and dataset can be loaded.

## Retention

Dry run:

```bash
python manage.py purge_old_cases --days 365
```

Delete:

```bash
python manage.py purge_old_cases --days 365 --confirm
```

Cases marked **Legal hold** and their matching audit event are excluded from
retention deletion. Legal-hold release must follow the organization’s approved
legal process.

## Model monitoring

```bash
python -m src.monitor_model --data incoming.csv
python -m src.validate_external --data mature_outcomes.csv
```

Investigate drift, calibration deterioration, subgroup changes, unusual override
rates, input failures, and sudden review-volume changes before changing policy.

## Incident and rollback

1. Disable API scoring by removing `SCORING_API_KEY`.
2. Preserve logs, case records, model manifest, and deployed revision.
3. Roll back application and model artifacts together.
4. Verify `/readyz/`, a controlled test score, and database migrations.
5. Document scope, affected cases, remediation, and required re-review.
