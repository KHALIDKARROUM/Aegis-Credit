# Operations Guide

## Production baseline

- Set `DEBUG=False`, `LOGIN_REQUIRED=True`, and strong independent secrets.
- Inject secrets with the deployment secret manager or a local, uncommitted
  `.env` file (mode 0600). `SECRET_KEY`, `AUDIT_HMAC_KEY`,
  `FIELD_ENCRYPTION_KEY`, `BACKUP_ENCRYPTION_KEY`, and
  `MODEL_SIGNING_PUBLIC_KEY` are mandatory; the service will not start
  without them.
- Use PostgreSQL through `DATABASE_URL`.
- Run migrations and `bootstrap_roles` during deployment.
- Create named analyst/reviewer accounts; do not share credentials.
- Restrict admin access and rotate API keys.
- Schedule retention, backup, restore, dependency, and security reviews.

Docker Compose only binds the web service to `127.0.0.1:8000`; place it behind
an authenticated TLS reverse proxy if remote access is required. Compose also
runs the retention command daily by default. Monitor that container and use
the same approved schedule in non-Compose deployments.

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

## Encryption, backups, and data-subject deletion

Case score inputs, explanations, reviewer notes, and batch results are
encrypted at field level with Fernet before database storage. Keep the field
encryption key in a managed secret store, restrict it to the application, and
rotate it through a controlled decrypt/re-encrypt migration. Database storage,
volumes, and snapshots still require provider-level encryption at rest.

Create only encrypted PostgreSQL backups; the command never writes a plaintext
dump to disk:

```bash
python manage.py backup_database --destination /secure/backups
```

Store the resulting `.fernet` file and `BACKUP_ENCRYPTION_KEY` separately, test
restores in an isolated environment, and include backup copies in retention and
deletion handling. For a verified data-subject request, record the authority,
identity-verification outcome, scope, operator, and completion time in the
organization's privacy register, then run a dry run followed by deletion:

```bash
python manage.py delete_subject_data --applicant-reference SUBJECT-123
python manage.py delete_subject_data --applicant-reference SUBJECT-123 --confirm
```

Legal holds override routine deletion until formally released. The command
deletes matching cases, their prediction audits, and batch records containing
the reference; backup copies are handled under the documented backup lifecycle.
Sensitive case/batch reads, exports, creation, and review changes are recorded
in `SensitiveDataAccessLog` without putting applicant values in the audit log.

## Signed model release

The checked-in model is deliberately rejected because its manifest records a
dirty worktree and the included data has not passed provenance review. Do not
edit that manifest to bypass the control. After independent provenance approval,
create a clean, tagged release commit and run the release job with a secret
manager providing `MODEL_SIGNING_PRIVATE_KEY` (base64 Ed25519 private key),
`MODEL_SIGNING_KEY_ID`, and `DATA_PROVENANCE_VERIFIED=True`:

```bash
git status --porcelain  # must produce no output
git tag -a model-vX.Y.Z -m "Model release X.Y.Z"
python -m src.train_model --release
```

The release job refuses an untagged/dirty commit or unapproved data, writes the
bundle to a content-addressed `models/releases/<sha256>/model.pkl` path, and
signs the canonical manifest. Deploy that release path and signed manifest as
immutable build assets; the runtime verifies the path, hash, tag, provenance
attestation, and Ed25519 signature using only the public key.

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
