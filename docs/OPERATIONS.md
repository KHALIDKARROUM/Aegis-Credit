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

Rotate `AUDIT_HMAC_KEY` without breaking case-reference lookup or in-flight
idempotency by placing the new key in `AUDIT_HMAC_KEY` and setting
`AUDIT_HMAC_KEYS` to `new-key,old-key`. Deploy that same ordered list to every
web, worker, and scheduled process. Keep an old key until all data, audit
records, and retry windows created with it have passed their approved retention
period; then remove it from the retained list. HMAC keys must never be reused
for encryption, signing, backups, or API credentials.

Docker Compose only binds the web service to `127.0.0.1:8000`; place it behind
an authenticated TLS reverse proxy if remote access is required. Compose also
runs the retention command daily by default. Monitor that container and use
the same approved schedule in non-Compose deployments. The Render Blueprint
includes a daily retention cron job at 03:17 UTC; monitor each run and adjust
the schedule only through an approved retention change.

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
encrypted at field level with Fernet before database storage. Keep field keys
in a managed secret store and restrict them to the application. Database
storage, volumes, and snapshots still require provider-level encryption at
rest.

Rotate field encryption in a maintenance/read-only window so a concurrent edit
cannot race the re-encryption pass:

1. Generate a new Fernet key. Keep the existing keys and a verified encrypted
   database backup in separately controlled storage.
2. Set `FIELD_ENCRYPTION_KEY` to the new key and set
   `FIELD_ENCRYPTION_KEYS` to a comma-separated list containing the new key
   first, followed by every old key still needed to read data or retained
   backups. Deploy this read-old/write-new configuration to every web and
   worker process. On Render, update the web secret and resync the Blueprint so
   the worker's `fromService` reference receives the same list before rotation.
3. Preview the affected model counts with
   `python manage.py rotate_field_encryption`, then run
   `python manage.py rotate_field_encryption --confirm`.
4. Verify representative records, run the application test suite, and create
   and test-restore a new encrypted database backup before resuming writes.
5. Remove an old read key only after all live ciphertext has been verified and
   every backup that may require that key has expired or been securely replaced.

Create only encrypted PostgreSQL backups; the command never writes a plaintext
dump to disk:

```bash
python manage.py backup_database --destination /secure/backups
```

The current streaming format uses a `.dump.brc` suffix. Verify its authentication
without changing a database, then restore only to an empty, isolated database
whose configured name is supplied explicitly:

```bash
python manage.py restore_database --backup /secure/backups/aegis-credit-TIMESTAMP.dump.brc
python manage.py restore_database --backup /secure/backups/aegis-credit-TIMESTAMP.dump.brc \
  --confirm-database isolated_restore_database
```

The restore command also recognizes legacy `.fernet` backups. Store every
backup and `BACKUP_ENCRYPTION_KEY` separately, test restores regularly, and
include backup copies in retention and deletion handling. For a verified
data-subject request, record the authority,
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

New queued batch uploads are stored as bounded, field-encrypted database
payloads and cleared after completion or cancellation, so web and worker
processes do not require a shared media volume. `MEDIA_ROOT` and Django's
`default` storage remain only for legacy file-backed batches or future media.
Drain any legacy pending batches before moving to a worker without shared file
storage. If file-backed uploads are enabled again, use approved private durable
storage with encryption and the same retention/deletion policy as case data.
The batch worker renews a database lease while processing. It automatically
recovers an interrupted job after `BATCH_LEASE_SECONDS` (default 300 seconds)
and stops retrying after `BATCH_MAX_ATTEMPTS` (default 3). Alert on failed jobs
and repeated lease recovery; do not raise the attempt cap without investigating
the underlying parsing, model, database, or capacity failure.

## Scoring API credential rotation

Configure `SCORING_API_KEYS` as a secret-manager value containing a JSON object
whose client ids identify individual integrations and whose secrets are at least
32 characters, for example `{"partner-a":"<random-secret-at-least-32-characters>"}`.
Do not commit or log this value. To rotate a credential without an outage, add a
new client id (for example `partner-a-next`), deploy it to the caller, confirm
traffic has moved, then remove the old entry. Distinct clients must not share a
secret. `SCORING_API_KEY` remains only as a deprecated compatibility credential
identified as client `legacy`; migrate callers to the JSON mapping before
removing it.

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

Those commands require the signed active release. Add `--allow-unsigned-demo`
only when explicitly exercising the checked-in local demonstration artifact;
never use that escape hatch in a shared deployment.

Persisted monitoring evidence must be recomputed from a representative raw
application CSV, not imported from a prebuilt drift report. Preview the run,
then repeat with `--confirm` after reviewing the row count and alert summary:

```bash
python manage.py record_monitoring_run incoming.csv \
  --window-start 2026-07-01 --window-end 2026-07-31 \
  --as-of 2026-08-01 --owner "Model Risk"
python manage.py record_monitoring_run incoming.csv \
  --window-start 2026-07-01 --window-end 2026-07-31 \
  --as-of 2026-08-01 --owner "Model Risk" --confirm
```

The command requires at least `MONITORING_MIN_SAMPLE_SIZE` valid rows (default
100), binds the run to the raw-input digest and active model release, and
recomputes drift and mature-outcome performance before persistence.

Leave `CURRENCY_CODE` blank until the dataset owner has documented and approved
the denomination in the data-provenance record; the interface will say
"monetary units." After approval, set the three-letter ISO 4217 code consistently
on every web deployment. This setting changes labels only and never converts
stored or submitted amounts.

Investigate drift, calibration deterioration, subgroup changes, unusual override
rates, input failures, and sudden review-volume changes before changing policy.

## Incident and rollback

1. Disable API scoring by removing every `SCORING_API_KEYS` entry and the
   deprecated `SCORING_API_KEY` compatibility value.
2. Preserve logs, case records, model manifest, and deployed revision.
3. Roll back application and model artifacts together.
4. Verify `/readyz/`, a controlled test score, and database migrations.
5. Document scope, affected cases, remediation, and required re-review.
