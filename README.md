# BankRisk Compass

BankRisk Compass is an end-to-end credit-risk screening and model-governance
project. It combines a calibrated machine-learning model with a human review
workflow, durable case records, batch applicant loading, monitoring, threshold
economics, authenticated API scoring, and deployment controls.

It is designed as a learning, portfolio, and controlled pilot system. It does
not approve or decline credit and does not generate compliant adverse-action
notices.

## Product capabilities

- blank-by-default applicant assessment with an explicit demo-data option;
- validated application-time inputs and unusual-value warnings;
- calibrated probability, reachable Low/Medium/High bands, and staff guidance;
- model-behavior explanations clearly separated from adverse-action reasons;
- durable assessment cases with notes, status, assignments, and documented overrides;
- idempotent web/API scoring and keyed audit fingerprints;
- CSV and Excel batch upload with row-level validation and downloadable results;
- operational volume, risk-mix, override, and drift monitoring;
- financial threshold scenarios using exposure, LGD, margin, and review cost;
- analyst, reviewer, and administrator access roles;
- OpenAPI documentation, API-key authentication, and rate limiting;
- SQLite for local use and PostgreSQL support for shared deployments;
- Windows launchers, Docker Compose, Render configuration, health checks, and CI.

## Current model

Version `2.1.0` selects the champion after each candidate has been calibrated and
given a threshold on separate data partitions.

| Model | Selection F1 | ROC-AUC | Brier score | Threshold |
|---|---:|---:|---:|---:|
| Gradient Boosting | 0.655 | 0.890 | 0.087 | 0.21 |
| Random Forest | 0.643 | 0.879 | 0.091 | 0.19 |
| Logistic Regression | 0.558 | 0.826 | 0.122 | 0.22 |

The selected calibrated Gradient Boosting model achieved these results on the
untouched final test set:

| Policy | Accuracy | Precision | Recall | F1 | ROC-AUC |
|---|---:|---:|---:|---:|---:|
| Threshold 0.50 | 0.884 | 0.880 | 0.543 | 0.672 | 0.881 |
| Screening threshold 0.21 | 0.828 | 0.582 | 0.755 | 0.657 | 0.881 |

At `0.21`, 28.4% of the test population is routed to review, compared with
13.5% at `0.50`. The included 5:1 cost ratio remains illustrative. The Business
Policy page lets reviewers replace it with explicit financial assumptions
without silently changing the live model.

## Validation design

The cleaned dataset is divided into five non-overlapping partitions:

- training: 19,449 rows;
- model selection: 2,593 rows;
- probability calibration: 1,945 rows;
- threshold selection: 1,945 rows;
- final test: 6,484 rows.

Preprocessing remains inside scikit-learn pipelines. Feature-reference and drift
baselines are built from training rows only. Loan grade and interest rate are
excluded from application-time scoring because they may be lender-assigned.
Age is excluded from the score and used only for plausibility checks and limited
monitoring.

## Quick start

### Local development (one command)

Install Python 3.12 or newer, then run this from the project directory:

```bash
python run.py
```

On Windows, `py run.py` works too, or double-click `Start BankRisk Compass.bat`.
The command creates `.venv`, installs only the dashboard dependencies when
needed, creates persistent local development keys, applies migrations, and
opens `http://127.0.0.1:8000/`. Subsequent launches reuse the environment and
keys, so locally encrypted case records remain readable.

Use `python run.py --no-browser` on a headless machine and
`python run.py --check` to validate the setup without starting the server.
Local access control is disabled by default because the server listens only on
`127.0.0.1`. The launcher does not bypass model-release or data-provenance
controls; the included demonstration artifact remains non-operational.

### Windows with Docker Desktop

Double-click `Start BankRisk Compass Docker.bat`. This starts the application
and a durable local PostgreSQL database.

### Any platform with Docker

```bash
docker compose up --build
```

### Developer setup

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py bootstrap_roles
python manage.py runserver
```

On macOS/Linux, activate with `source .venv/bin/activate`.

## Authentication and roles

Set `LOGIN_REQUIRED=True` for any shared deployment. Create role groups and an
optional first administrator with:

```bash
python manage.py bootstrap_roles
```

The optional environment variables are:

```text
BOOTSTRAP_ADMIN_USERNAME
BOOTSTRAP_ADMIN_PASSWORD
BOOTSTRAP_ADMIN_EMAIL
```

Roles:

- **Analysts** can score, load batches, and view cases.
- **Reviewers** can also edit case status, record overrides, and view governance pages.
- **Administrators** have reviewer access plus Django administration.

## Batch applicant loading

Open `/batch/` or download `/batch/template.csv`. Supported files are `.csv`
and `.xlsx`. Required columns:

```text
person_age
person_income
person_emp_length
person_home_ownership
loan_amnt
loan_intent
cb_person_cred_hist_length
cb_person_default_on_file
```

`applicant_reference` is optional. Use an internal case number, not a name,
account number, or government identifier. Invalid rows are reported separately
and are not scored.

## Scoring API

Set `SCORING_API_KEY`, then use:

```text
POST /api/v1/score/
X-API-Key: <key>
Idempotency-Key: <UUID>
Content-Type: application/json
```

Interactive documentation is at `/api/docs/`; the OpenAPI document is at
`/api/v1/openapi.json`.

The endpoint uses the same validation contract as the web form, enforces a
configurable per-minute limit, stores a case, and returns the same result when
an idempotency key is replayed. It deliberately omits local explanations for
latency and governance reasons.

## Monitoring and validation commands

Compare incoming feature distributions with the training baseline:

```bash
python -m src.monitor_model --data path/to/new_applicants.csv
```

Evaluate a labeled external or out-of-time sample:

```bash
python -m src.validate_external --data path/to/mature_outcomes.csv
```

Preview or execute data retention:

```bash
python manage.py purge_old_cases --days 365
python manage.py purge_old_cases --days 365 --confirm
```

Release retraining (only after data provenance approval):

```bash
python -m src.train_model --release
```

Add `--quick` only for an approved short release-validation run. The command
requires a clean worktree, exactly one tag at `HEAD`, approved data provenance,
and an Ed25519 private signing key supplied through a secret manager. The
checked-in demonstration artifact is intentionally not eligible for scoring.

## Production configuration

Copy `.env.example` as a reference. Important settings include:

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Django cryptographic secret |
| `AUDIT_HMAC_KEY` | Separate key for applicant-feature fingerprints |
| `FIELD_ENCRYPTION_KEY` | Fernet key for persisted applicant fields |
| `BACKUP_ENCRYPTION_KEY` | Separate Fernet key for database backups |
| `MODEL_SIGNING_PUBLIC_KEY` | Ed25519 public key used to verify model releases |
| `DATABASE_URL` | PostgreSQL connection URL |
| `LOGIN_REQUIRED` | Enforce staff authentication |
| `SCORING_API_KEY` | Enable API scoring |
| `API_RATE_LIMIT_PER_MINUTE` | API request ceiling |
| `CASE_RETENTION_DAYS` | Retention-command default |
| `DATA_PROVENANCE_VERIFIED` | Enables only formally approved training data |
| `MAX_BATCH_ROWS` | Batch row limit |
| `MAX_UPLOAD_BYTES` | Upload size limit |

Shared deployments must use PostgreSQL. SQLite is intentionally retained only
for local single-user operation.

## Project structure

```text
app/                  Django workflows, templates, forms, models, and tests
bankrisk_compass/     Django settings and URL configuration
data/                 Demonstration dataset
models/               Versioned model bundle and integrity manifest
reports/              Generated evaluation and governance reports
src/                  Training, drift monitoring, and external validation
docs/                 User and operations guidance
Dockerfile            Production-style container image
docker-compose.yml    Local PostgreSQL deployment
render.yaml           Render web service and PostgreSQL blueprint
MODEL_CARD.md          Intended use, metrics, limitations, and controls
DATA_CARD.md           Data quality, representation, privacy, and provenance
```

The externally owned production gates are tracked in
`docs/GOVERNANCE_CHECKLIST.md`.
Setup failures and removal steps are covered in `docs/TROUBLESHOOTING.md`.

## Verification

```bash
python manage.py migrate
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
python -m compileall -q app bankrisk_compass src
python -m pip check
```

## Licensing and provenance

Project source code is licensed under the MIT License. The included dataset is
not covered by that license. Its exact upstream source and redistribution terms
are not established in the repository; see `DATA_PROVENANCE.md`.

Do not redistribute or operationalize the dataset until provenance, permission,
geographic scope, collection period, definitions, and representativeness have
been independently confirmed.

## What code cannot complete

Real lending use still requires organization-specific work:

- representative bank and product data with mature outcomes;
- approved PD/LGD/EAD and profitability assumptions;
- independent model validation and change approval;
- legal and fair-lending review using appropriate protected-class analysis;
- validated, specific adverse-action reason mapping;
- penetration testing, incident response, backups, and recovery exercises;
- human staffing, service-level targets, override governance, and periodic review.

The system is decision support. It must not be treated as an autonomous credit
decision engine.
